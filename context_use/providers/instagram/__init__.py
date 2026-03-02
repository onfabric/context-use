from context_use.providers.instagram.comments import (
    COMMENTS_POSTS_CONFIG as _COMMENTS_POSTS_CONFIG,
)
from context_use.providers.instagram.comments import (
    COMMENTS_REELS_CONFIG as _COMMENTS_REELS_CONFIG,
)
from context_use.providers.instagram.comments import (
    InstagramCommentPostsPipe,
    InstagramCommentReelsPipe,
)
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
from context_use.providers.instagram.likes import (
    LIKED_POSTS_CONFIG as _LIKED_POSTS_CONFIG,
)
from context_use.providers.instagram.likes import (
    STORY_LIKES_CONFIG as _STORY_LIKES_CONFIG,
)
from context_use.providers.instagram.likes import (
    InstagramLikedPostsPipe,
    InstagramStoryLikesPipe,
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
from context_use.providers.instagram.saved import (
    SAVED_COLLECTIONS_CONFIG as _SAVED_COLLECTIONS_CONFIG,
)
from context_use.providers.instagram.saved import (
    SAVED_POSTS_CONFIG as _SAVED_POSTS_CONFIG,
)
from context_use.providers.instagram.saved import (
    InstagramSavedCollectionsPipe,
    InstagramSavedPostsPipe,
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
        _LIKED_POSTS_CONFIG,
        _STORY_LIKES_CONFIG,
        _COMMENTS_POSTS_CONFIG,
        _COMMENTS_REELS_CONFIG,
        _FOLLOWERS_CONFIG,
        _FOLLOWING_CONFIG,
        _SAVED_POSTS_CONFIG,
        _SAVED_COLLECTIONS_CONFIG,
    ]
)

__all__ = [
    "InstagramCommentPostsPipe",
    "InstagramCommentReelsPipe",
    "InstagramFollowersPipe",
    "InstagramFollowingPipe",
    "InstagramLikedPostsPipe",
    "InstagramMediaRecord",
    "InstagramPostsViewedPipe",
    "InstagramPostsViewedV0Pipe",
    "InstagramProfileSearchesPipe",
    "InstagramReelsPipe",
    "InstagramSavedCollectionsPipe",
    "InstagramSavedPostsPipe",
    "InstagramStoriesPipe",
    "InstagramStoryLikesPipe",
    "InstagramVideosWatchedPipe",
    "InstagramVideosWatchedV0Pipe",
    "PROVIDER_CONFIG",
]
