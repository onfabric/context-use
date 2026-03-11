from __future__ import annotations

from context_use.testing.fixtures import load_fixture

_BASE = "users/alice/instagram"

INSTAGRAM_STORIES_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/media/stories.json"
)
INSTAGRAM_REELS_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/media/reels.json"
)
INSTAGRAM_POSTS_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/media/posts_1.json"
)

INSTAGRAM_VIDEOS_WATCHED_V0_JSON: dict = load_fixture(
    f"{_BASE}/v0/ads_information/ads_and_topics/videos_watched.json"
)
INSTAGRAM_VIDEOS_WATCHED_V1_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/ads_information/ads_and_topics/videos_watched.json"
)

INSTAGRAM_POSTS_VIEWED_V0_JSON: dict = load_fixture(
    f"{_BASE}/v0/ads_information/ads_and_topics/posts_viewed.json"
)
INSTAGRAM_POSTS_VIEWED_V1_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/ads_information/ads_and_topics/posts_viewed.json"
)

INSTAGRAM_PROFILE_SEARCHES_JSON: dict = load_fixture(
    f"{_BASE}/v1/logged_information/recent_searches/profile_searches.json"
)

INSTAGRAM_LIKED_POSTS_V0_JSON: dict = load_fixture(
    f"{_BASE}/v0/your_instagram_activity/likes/liked_posts.json"
)
INSTAGRAM_LIKED_POSTS_V1_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/likes/liked_posts.json"
)

INSTAGRAM_STORY_LIKES_V0_JSON: dict = load_fixture(
    f"{_BASE}/v0/your_instagram_activity/story_interactions/story_likes.json"
)
INSTAGRAM_STORY_LIKES_V1_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/story_interactions/story_likes.json"
)

INSTAGRAM_POST_COMMENTS_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/comments/post_comments_1.json"
)
INSTAGRAM_REELS_COMMENTS_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/comments/reels_comments.json"
)

INSTAGRAM_FOLLOWERS_JSON: list[dict] = load_fixture(
    f"{_BASE}/v1/connections/followers_and_following/followers_1.json"
)
INSTAGRAM_FOLLOWING_JSON: dict = load_fixture(
    f"{_BASE}/v1/connections/followers_and_following/following.json"
)

INSTAGRAM_SAVED_POSTS_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/saved/saved_posts.json"
)
INSTAGRAM_SAVED_COLLECTIONS_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/saved/saved_collections.json"
)

INSTAGRAM_DM_INBOX_JSON: dict = load_fixture(
    f"{_BASE}/v1/your_instagram_activity/messages/inbox/bobsmith_1234567890/message_1.json"
)
