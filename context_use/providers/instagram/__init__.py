from context_use.providers.instagram import (
    comments,
    connections,
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
        comments,
        connections,
        likes,
        media,
        posts_viewed,
        profile_searches,
        saved,
        videos_watched,
    ],
)

__all__ = ["PROVIDER"]
