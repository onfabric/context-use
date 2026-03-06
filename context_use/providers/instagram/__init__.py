from context_use.providers.instagram import (  # noqa: F401 — triggers register_interaction
    comments,
    connections,
    likes,
    media,
    posts_viewed,
    profile_searches,
    saved,
    videos_watched,
)
from context_use.providers.registry import build_and_register_provider

PROVIDER = "instagram"
build_and_register_provider(PROVIDER)

__all__ = ["PROVIDER"]
