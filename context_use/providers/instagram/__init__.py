from context_use.providers.instagram import (  # noqa: F401 — triggers register_interaction for each config
    comments,
    connections,
    likes,
    media,
    posts_viewed,
    profile_searches,
    saved,
    videos_watched,
)
from context_use.providers.instagram.comments import (
    InstagramCommentPostsPipe,
    InstagramCommentReelsPipe,
)
from context_use.providers.instagram.connections import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
from context_use.providers.instagram.likes import (
    InstagramLikedPostsPipe,
    InstagramLikedPostsV0Pipe,
    InstagramStoryLikesPipe,
    InstagramStoryLikesV0Pipe,
)
from context_use.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.providers.instagram.posts_viewed import (
    InstagramPostsViewedPipe,
    InstagramPostsViewedV0Pipe,
)
from context_use.providers.instagram.profile_searches import (
    InstagramProfileSearchesPipe,
)
from context_use.providers.instagram.saved import (
    InstagramSavedCollectionsPipe,
    InstagramSavedPostsPipe,
)
from context_use.providers.instagram.schemas import InstagramMediaRecord
from context_use.providers.instagram.videos_watched import (
    InstagramVideosWatchedPipe,
    InstagramVideosWatchedV0Pipe,
)
from context_use.providers.registry import build_and_register_provider

PROVIDER = "instagram"
build_and_register_provider(PROVIDER)

__all__ = [
    "InstagramCommentPostsPipe",
    "InstagramCommentReelsPipe",
    "InstagramFollowersPipe",
    "InstagramFollowingPipe",
    "InstagramLikedPostsPipe",
    "InstagramLikedPostsV0Pipe",
    "InstagramMediaRecord",
    "InstagramPostsViewedPipe",
    "InstagramPostsViewedV0Pipe",
    "InstagramProfileSearchesPipe",
    "InstagramReelsPipe",
    "InstagramSavedCollectionsPipe",
    "InstagramSavedPostsPipe",
    "InstagramStoriesPipe",
    "InstagramStoryLikesPipe",
    "InstagramStoryLikesV0Pipe",
    "InstagramVideosWatchedPipe",
    "InstagramVideosWatchedV0Pipe",
    "PROVIDER",
]
