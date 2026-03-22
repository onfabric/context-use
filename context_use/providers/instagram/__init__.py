from context_use.providers.instagram import (
    ads_clicked,
    ads_viewed,
    comments,
    connections,
    direct_messages,
    liked_posts,
    media,
    posts_viewed,
    profile_searches,
    saved,
    story_likes,
    videos_watched,
)
from context_use.providers.instagram.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[
        ads_clicked,
        ads_viewed,
        comments,
        connections,
        direct_messages,
        liked_posts,
        media,
        posts_viewed,
        profile_searches,
        saved,
        story_likes,
        videos_watched,
    ],
)

__all__ = ["PROVIDER"]
