from context_use.providers.instagram import (  # noqa: F401 — triggers declare_interaction
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

register_provider(PROVIDER)

__all__ = ["PROVIDER"]
