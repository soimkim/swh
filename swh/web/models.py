# Copyright (C) 2024-2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU Affero General Public License version 3, or any later version
# See top-level LICENSE file for more information

from django.db import models


class ContentOriginMapping(models.Model):
    """
    Model to store the mapping between content objects and their origin URLs.
    This allows us to track which origin a content object was saved from.
    """
    
    content_sha1_git = models.CharField(max_length=40, db_index=True, help_text="SHA1 Git hash of the content object")
    origin_url = models.CharField(max_length=4096, help_text="Origin URL where this content was saved from")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this mapping was created")
    
    class Meta:
        app_label = "swh_web_save_code_now"
        db_table = "content_origin_mapping"
        indexes = [
            models.Index(fields=["content_sha1_git"]),
            models.Index(fields=["origin_url"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_sha1_git", "origin_url"],
                name="unique_content_origin_mapping"
            ),
        ]
    
    def __str__(self):
        return f"Content {self.content_sha1_git} from {self.origin_url}"
