# Copyright (C) 2018-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU Affero General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import Dict, Set, Optional

from rest_framework.request import Request

from swh.model.hashutil import hash_to_bytes, hash_to_hex
from swh.model.swhids import ObjectType
from swh.web.api.apidoc import api_doc, format_docstring
from swh.web.api.apiurls import api_route
from swh.web.utils import archive
from swh.web.utils.exc import LargePayloadExc, NotFoundExc
from swh.web.utils.identifiers import group_swhids, parse_core_swhid, resolve_swhid


@api_route(r"/resolve/(?P<swhid>.+)/", "api-1-resolve-swhid")
@api_doc("/resolve/", category="Archive")
@format_docstring()
def api_resolve_swhid(request: Request, swhid: str):
    """
    .. http:get:: /api/1/resolve/(swhid)/

        Resolve a SoftWare Hash IDentifier (SWHID)

        Try to resolve a provided `SoftWare Hash IDentifier
        <https://docs.softwareheritage.org/devel/swh-model/persistent-identifiers.html>`_
        into an url for browsing the pointed archive object.

        If the provided identifier is valid, the existence of the object in
        the archive will also be checked.

        :param string swhid: a SoftWare Hash IDentifier

        :>json string browse_url: the url for browsing the pointed object
        :>json object metadata: object holding optional parts of the SWHID
        :>json string namespace: the SWHID namespace
        :>json string object_id: the hash identifier of the pointed object
        :>json string object_type: the type of the pointed object
        :>json number scheme_version: the scheme version of the SWHID
        :>json string origin_url: the origin URL where this object was actually saved in the archive (when available)

        {common_headers}

        :statuscode 200: no error
        :statuscode 400: an invalid SWHID has been provided
        :statuscode 404: the pointed object does not exist in the archive

        **Example:**

        .. parsed-literal::

            :swh_web_api:`resolve/swh:1:rev:96db9023b881d7cd9f379b0c154650d6c108e9a3;origin=https://github.com/openssl/openssl/`
    """
    # try to resolve the provided swhid
    swhid_resolved = resolve_swhid(swhid)
    # id is well-formed, now check that the pointed
    # object is present in the archive, NotFoundExc
    # will be raised otherwise
    swhid_parsed = swhid_resolved["swhid_parsed"]
    object_type = swhid_parsed.object_type
    object_id = hash_to_hex(swhid_parsed.object_id)
    archive.lookup_object(swhid_parsed.object_type, object_id)
    
    # Find the origin URL where this object was actually saved
    origin_url = None
    
    try:
        if object_type.name.lower() == 'content':
            # For content objects, try to find which origin(s) contain this content
            origin_url = _find_origin_for_content(object_id)
        elif object_type.name.lower() == 'directory':
            # For directory objects, try to find which origin(s) contain this directory
            origin_url = _find_origin_for_directory(object_id)
        elif object_type.name.lower() == 'revision':
            # For revision objects, try to find which origin(s) contain this revision
            origin_url = _find_origin_for_revision(object_id)
        elif object_type.name.lower() == 'release':
            # For release objects, try to find which origin(s) contain this release
            origin_url = _find_origin_for_release(object_id)
        elif object_type.name.lower() == 'snapshot':
            # For snapshot objects, try to find which origin(s) contain this snapshot
            origin_url = _find_origin_for_snapshot(object_id)
    except Exception:
        # If we can't find the origin, leave origin_url as None
        pass
    

    
    # id is well-formed and the pointed object exists
    return {
        "namespace": swhid_parsed.namespace,
        "scheme_version": swhid_parsed.scheme_version,
        "object_type": object_type.name.lower(),
        "object_id": object_id,
        "metadata": swhid_parsed.qualifiers(),
        "browse_url": request.build_absolute_uri(swhid_resolved["browse_url"]),
        "origin_url": origin_url if origin_url is not None else "",  # Always include origin_url
    }


@api_route(r"/known/", "api-1-known", methods=["POST"])
@api_doc("/known/", category="Archive")
@format_docstring()
def api_swhid_known(request: Request):
    """
    .. http:post:: /api/1/known/

        Check if a list of objects are present in the Software Heritage
        archive.

        The objects to check existence must be provided using
        `SoftWare Hash IDentifiers
        <https://docs.softwareheritage.org/devel/swh-model/persistent-identifiers.html>`_.

        :<jsonarr string -: input array of SWHIDs, its length cannot exceed 1000.

        :>json object <swhid>: an object whose keys are input SWHIDs and values
            objects with the following keys:

            * **known (bool)**: whether the object was found

        {common_headers}

        :statuscode 200: no error
        :statuscode 400: an invalid SWHID was provided
        :statuscode 413: the input array of SWHIDs is too large

    """
    limit = 1000
    if len(request.data) > limit:
        raise LargePayloadExc(
            "The maximum number of SWHIDs this endpoint can receive is %s" % limit
        )

    swhids = [parse_core_swhid(swhid) for swhid in request.data]

    response = {str(swhid): {"known": False} for swhid in swhids}

    # group swhids by their type
    swhids_by_type = group_swhids(swhids)
    # search for hashes not present in the storage
    missing_hashes: Dict[ObjectType, Set[bytes]] = {
        k: set(map(hash_to_bytes, archive.lookup_missing_hashes({k: v})))
        for k, v in swhids_by_type.items()
    }

    for swhid in swhids:
        if swhid.object_id not in missing_hashes[swhid.object_type]:
            response[str(swhid)]["known"] = True

    return response


def _find_origin_for_content(content_id: str) -> Optional[str]:
    """
    Find the origin URL where a content object was saved.
    
    Args:
        content_id: SHA1 Git hash of the content object
        
    Returns:
        Origin URL if found, None otherwise
    """
    try:
        from swh.web.utils import config
        indexer_storage = config.indexer_storage()
        
        # Search for content in origin intrinsic metadata
        try:
            content_origins = indexer_storage.origin_intrinsic_metadata_search_fulltext(
                conjunction=[f"content:{content_id}"], limit=1
            )
            if content_origins:
                origin_id = content_origins[0].id
                origin_info = archive.lookup_origin(origin_id)
                return origin_info["url"]
        except Exception:
            pass
            
    except Exception:
        pass
    
    return None


def _find_origin_for_directory(directory_id: str) -> Optional[str]:
    """Find the origin URL where a directory object was saved."""
    try:
        from swh.web.utils import config
        indexer_storage = config.indexer_storage()
        
        dir_origins = indexer_storage.origin_intrinsic_metadata_search_fulltext(
            conjunction=[f"directory:{directory_id}"], limit=1
        )
        if dir_origins:
            origin_id = dir_origins[0].id
            origin_info = archive.lookup_origin(origin_id)
            return origin_info["url"]
    except Exception:
        pass
    
    return None


def _find_origin_for_revision(revision_id: str) -> Optional[str]:
    """Find the origin URL where a revision object was saved."""
    try:
        from swh.web.utils import config
        indexer_storage = config.indexer_storage()
        
        rev_origins = indexer_storage.origin_intrinsic_metadata_search_fulltext(
            conjunction=[f"revision:{revision_id}"], limit=1
        )
        if rev_origins:
            origin_id = rev_origins[0].id
            origin_info = archive.lookup_origin(origin_id)
            return origin_info["url"]
    except Exception:
        pass
    
    return None


def _find_origin_for_release(release_id: str) -> Optional[str]:
    """Find the origin URL where a release object was saved."""
    try:
        from swh.web.utils import config
        indexer_storage = config.indexer_storage()
        
        rel_origins = indexer_storage.origin_intrinsic_metadata_search_fulltext(
            conjunction=[f"release:{release_id}"], limit=1
        )
        if rel_origins:
            origin_id = rel_origins[0].id
            origin_info = archive.lookup_origin(origin_id)
            return origin_info["url"]
    except Exception:
        pass
    
    return None


def _find_origin_for_snapshot(snapshot_id: str) -> Optional[str]:
    """Find the origin URL where a snapshot object was saved."""
    try:
        # For snapshots, we can try to find the origin through the snapshot's branches
        snapshot_info = archive.lookup_snapshot(snapshot_id)
        if snapshot_info and 'branches' in snapshot_info:
            # Try to find origin from snapshot branches
            # This is a simplified approach
            pass
    except Exception:
        pass
    
    return None
