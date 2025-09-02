# Copyright (C) 2024-2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU Affero General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import List, Optional
from swh.model.hashutil import hash_to_hex
from swh.web.models import ContentOriginMapping


def save_content_origin_mapping(content_sha1_git: str, origin_url: str) -> None:
    """
    Save the mapping between a content object and its origin URL.
    
    Args:
        content_sha1_git: SHA1 Git hash of the content object
        origin_url: Origin URL where this content was saved from
    """
    try:
        # Create or update the mapping
        mapping, created = ContentOriginMapping.objects.get_or_create(
            content_sha1_git=content_sha1_git,
            origin_url=origin_url,
            defaults={'content_sha1_git': content_sha1_git, 'origin_url': origin_url}
        )
        if created:
            print(f"Created content-origin mapping: {content_sha1_git} -> {origin_url}")
    except Exception as e:
        print(f"Error saving content-origin mapping: {e}")


def get_origin_for_content(content_sha1_git: str) -> Optional[str]:
    """
    Get the origin URL for a content object.
    
    Args:
        content_sha1_git: SHA1 Git hash of the content object
        
    Returns:
        Origin URL if found, None otherwise
    """
    try:
        mapping = ContentOriginMapping.objects.filter(
            content_sha1_git=content_sha1_git
        ).first()
        
        if mapping:
            return mapping.origin_url
    except Exception as e:
        print(f"Error getting origin for content: {e}")
    
    return None


def get_origins_for_content(content_sha1_git: str) -> List[str]:
    """
    Get all origin URLs for a content object (content can exist in multiple origins).
    
    Args:
        content_sha1_git: SHA1 Git hash of the content object
        
    Returns:
        List of origin URLs
    """
    try:
        mappings = ContentOriginMapping.objects.filter(
            content_sha1_git=content_sha1_git
        ).values_list('origin_url', flat=True)
        
        return list(mappings)
    except Exception as e:
        print(f"Error getting origins for content: {e}")
    
    return []


def save_content_origin_mappings_from_directory(directory_contents: List, origin_url: str) -> None:
    """
    Save origin mappings for all content objects in a directory.
    
    Args:
        directory_contents: List of content objects from a directory
        origin_url: Origin URL where these contents were saved from
    """
    for content in directory_contents:
        if hasattr(content, 'sha1_git'):
            content_sha1_git = hash_to_hex(content.sha1_git)
            save_content_origin_mapping(content_sha1_git, origin_url)
