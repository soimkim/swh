# Copyright (C) 2024-2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU Affero General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import Dict, List, Optional, Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q
import json

from swh.web.utils import archive
from swh.web.utils.exc import NotFoundExc
from swh.web.save_code_now.models import SaveOriginRequest


@require_http_methods(["GET"])
def origin_files_admin(request: HttpRequest) -> HttpResponse:
    """
    Admin view to browse files by origin URL.
    
    Args:
        request: HTTP request object
        
    Returns:
        Rendered admin template with origin files data
    """
    origin_url = request.GET.get('origin_url', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))
    
    context = {
        'origin_url': origin_url,
        'page': page,
        'per_page': per_page,
    }
    
    if origin_url:
        try:
            # Get origin info
            origin_info = archive.lookup_origin(origin_url)
            context['origin_info'] = origin_info
            
            # Get save requests for this origin
            save_requests = SaveOriginRequest.objects.filter(
                origin_url=origin_url
            ).order_by('-request_date')
            context['save_requests'] = save_requests
            
            # Get latest snapshot context
            try:
                from swh.web.browse.snapshot_context import get_snapshot_context
                snapshot_context = get_snapshot_context(origin_url=origin_url)
                context['snapshot_context'] = snapshot_context
                
                # Get files from the latest snapshot
                files_data = _get_files_from_snapshot(snapshot_context, page, per_page)
                context.update(files_data)
                
            except NotFoundExc:
                context['error'] = f"No snapshot found for origin: {origin_url}"
                
        except NotFoundExc:
            context['error'] = f"Origin not found: {origin_url}"
    
    return render(request, 'admin/origin_files_admin.html', context)


@require_http_methods(["GET"])
def origin_files_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get files data for a specific origin.
    
    Args:
        request: HTTP request object
        
    Returns:
        JSON response with files data
    """
    origin_url = request.GET.get('origin_url', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))
    
    if not origin_url:
        return JsonResponse({'error': 'origin_url parameter is required'}, status=400)
    
    try:
        # Get origin info
        origin_info = archive.lookup_origin(origin_url)
        
        # Get latest snapshot context
        from swh.web.browse.snapshot_context import get_snapshot_context
        snapshot_context = get_snapshot_context(origin_url=origin_url)
        
        # Get files from the latest snapshot
        files_data = _get_files_from_snapshot(snapshot_context, page, per_page)
        
        return JsonResponse({
            'origin_info': origin_info,
            'snapshot_context': {
                'snapshot_id': snapshot_context['snapshot_id'],
                'visit_info': snapshot_context['visit_info'],
            },
            'files': files_data['files'],
            'pagination': files_data['pagination'],
        })
        
    except NotFoundExc as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)


def _get_files_from_snapshot(snapshot_context: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
    """
    Get files from a snapshot context with pagination.
    
    Args:
        snapshot_context: Snapshot context data
        page: Page number
        per_page: Items per page
        
    Returns:
        Dictionary with files data and pagination info
    """
    files = []
    pagination = {}
    
    try:
        # Get root directory
        root_directory_id = snapshot_context.get('root_directory')
        if not root_directory_id:
            return {'files': [], 'pagination': pagination}
        
        # Get directory contents
        directory_info = archive.lookup_directory(root_directory_id)
        
        # Process directory entries
        for entry in directory_info.get('entries', []):
            if entry['type'] == 'file':
                # Generate SWHID for the file
                from swh.web.utils.identifiers import gen_swhid
                from swh.model.swhids import ObjectType
                
                file_swhid = gen_swhid(
                    ObjectType.CONTENT,
                    entry['sha1_git'],
                    metadata={
                        'origin': snapshot_context['origin_info']['url'],
                        'visit': gen_swhid(ObjectType.SNAPSHOT, snapshot_context['snapshot_id']),
                    }
                )
                
                files.append({
                    'name': entry['name'],
                    'path': entry['name'],
                    'swhid': file_swhid,
                    'sha1_git': entry['sha1_git'],
                    'size': entry.get('length', 0),
                    'permissions': entry.get('perms', 0),
                    'origin_url': snapshot_context['origin_info']['url'],
                })
        
        # Paginate results
        paginator = Paginator(files, per_page)
        page_obj = paginator.get_page(page)
        
        pagination = {
            'current_page': page,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
            'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
        }
        
        return {
            'files': list(page_obj),
            'pagination': pagination,
        }
        
    except Exception as e:
        return {
            'files': [],
            'pagination': pagination,
            'error': f'Error getting files: {str(e)}'
        }
