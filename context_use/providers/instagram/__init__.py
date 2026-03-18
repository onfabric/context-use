from context_use.providers.instagram import (
    ads_viewed,
    comments,
    connections,
    direct_messages,
    likes,
    media,
    posts_viewed,
    profile_searches,
    saved,
    videos_watched,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[
        ads_viewed,
        comments,
        connections,
        direct_messages,
        likes,
        media,
        posts_viewed,
        profile_searches,
        saved,
        videos_watched,
    ],
)

__all__ = ["PROVIDER"]
