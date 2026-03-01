from context_use.providers.instagram.connections import (
    FOLLOWERS_CONFIG as _FOLLOWERS_CONFIG,
)
from context_use.providers.instagram.connections import (
    FOLLOWING_CONFIG as _FOLLOWING_CONFIG,
)
from context_use.providers.instagram.connections import (
    InstagramFollowersPipe,
    InstagramFollowingPipe,
)
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
from context_use.providers.instagram.schemas import InstagramMediaRecord
from context_use.providers.types import ProviderConfig

PROVIDER_CONFIG = ProviderConfig(
    interactions=[
        _STORIES_CONFIG,
        _REELS_CONFIG,
        _FOLLOWERS_CONFIG,
        _FOLLOWING_CONFIG,
    ]
)

__all__ = [
    "InstagramFollowersPipe",
    "InstagramFollowingPipe",
    "InstagramMediaRecord",
    "InstagramReelsPipe",
    "InstagramStoriesPipe",
    "PROVIDER_CONFIG",
]
