from context_use.providers.instagram.media import (
    REELS_CONFIG as _REELS_CONFIG,
)
from context_use.providers.instagram.media import (
    STORIES_CONFIG as _STORIES_CONFIG,
)
from context_use.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.providers.instagram.posts_viewed import (
    POSTS_VIEWED_V0_CONFIG as _POSTS_VIEWED_V0_CONFIG,
)
from context_use.providers.instagram.posts_viewed import (
    POSTS_VIEWED_V1_CONFIG as _POSTS_VIEWED_V1_CONFIG,
)
from context_use.providers.instagram.posts_viewed import (
    InstagramPostsViewedPipe,
    InstagramPostsViewedV0Pipe,
)
from context_use.providers.instagram.profile_searches import (
    PROFILE_SEARCHES_CONFIG as _PROFILE_SEARCHES_CONFIG,
)
from context_use.providers.instagram.profile_searches import (
    InstagramProfileSearchesPipe,
)
from context_use.providers.instagram.schemas import InstagramMediaRecord
from context_use.providers.instagram.videos_watched import (
    VIDEOS_WATCHED_V0_CONFIG as _VIDEOS_WATCHED_V0_CONFIG,
)
from context_use.providers.instagram.videos_watched import (
    VIDEOS_WATCHED_V1_CONFIG as _VIDEOS_WATCHED_V1_CONFIG,
)
from context_use.providers.instagram.videos_watched import (
    InstagramVideosWatchedPipe,
    InstagramVideosWatchedV0Pipe,
)
from context_use.providers.types import ProviderConfig

PROVIDER_CONFIG = ProviderConfig(
    interactions=[
        _STORIES_CONFIG,
        _REELS_CONFIG,
        _VIDEOS_WATCHED_V0_CONFIG,
        _VIDEOS_WATCHED_V1_CONFIG,
        _POSTS_VIEWED_V0_CONFIG,
        _POSTS_VIEWED_V1_CONFIG,
        _PROFILE_SEARCHES_CONFIG,
    ]
)

__all__ = [
    "InstagramMediaRecord",
    "InstagramPostsViewedPipe",
    "InstagramPostsViewedV0Pipe",
    "InstagramProfileSearchesPipe",
    "InstagramReelsPipe",
    "InstagramStoriesPipe",
    "InstagramVideosWatchedPipe",
    "InstagramVideosWatchedV0Pipe",
    "PROVIDER_CONFIG",
]
