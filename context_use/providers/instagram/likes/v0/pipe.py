from __future__ import annotations

from collections.abc import Iterator

from context_use.providers.instagram.likes.pipe import InstagramLikePipe
from context_use.providers.instagram.likes.record import InstagramLikedPostRecord
from context_use.providers.instagram.likes.v0.schemas import (
    InstagramLikedPostsManifest,
    InstagramStoryLikesManifest,
)
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


class InstagramLikedPostsPipe(InstagramLikePipe):
    interaction_type = "instagram_liked_posts"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/likes/liked_posts.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramLikedPostsManifest.model_validate_json(raw)
        for item in manifest.likes_media_likes:
            for entry in item.string_list_data:
                yield InstagramLikedPostRecord(
                    title=item.title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


class InstagramStoryLikesPipe(InstagramLikePipe):
    interaction_type = "instagram_story_likes"
    archive_version = 0
    archive_path_pattern = "your_instagram_activity/story_interactions/story_likes.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[InstagramLikedPostRecord]:
        raw = storage.read(source_uri)
        manifest = InstagramStoryLikesManifest.model_validate_json(raw)
        for item in manifest.story_activities_story_likes:
            for entry in item.string_list_data:
                yield InstagramLikedPostRecord(
                    title=item.title,
                    href=entry.href,
                    timestamp=entry.timestamp,
                    source=item.model_dump_json(),
                )


declare_interaction(InteractionConfig(pipe=InstagramStoryLikesPipe, memory=None))
