from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"
ALICE_INSTAGRAM_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v1"
ALICE_INSTAGRAM_V0_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v0"

INSTAGRAM_STORIES_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "media" / "stories.json"
    ).read_text()
)

INSTAGRAM_REELS_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "media" / "reels.json"
    ).read_text()
)

INSTAGRAM_POSTS_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "media" / "posts_1.json"
    ).read_text()
)

INSTAGRAM_VIDEOS_WATCHED_V0_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_V0_DIR
        / "ads_information"
        / "ads_and_topics"
        / "videos_watched.json"
    ).read_text()
)

INSTAGRAM_VIDEOS_WATCHED_V1_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "ads_information"
        / "ads_and_topics"
        / "videos_watched.json"
    ).read_text()
)

INSTAGRAM_POSTS_VIEWED_V0_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_V0_DIR
        / "ads_information"
        / "ads_and_topics"
        / "posts_viewed.json"
    ).read_text()
)

INSTAGRAM_POSTS_VIEWED_V1_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "ads_information" / "ads_and_topics" / "posts_viewed.json"
    ).read_text()
)

INSTAGRAM_PROFILE_SEARCHES_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "logged_information"
        / "recent_searches"
        / "profile_searches.json"
    ).read_text()
)

INSTAGRAM_LIKED_POSTS_V0_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_V0_DIR
        / "your_instagram_activity"
        / "likes"
        / "liked_posts.json"
    ).read_text()
)

INSTAGRAM_LIKED_POSTS_V1_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "likes" / "liked_posts.json"
    ).read_text()
)

INSTAGRAM_STORY_LIKES_V0_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_V0_DIR
        / "your_instagram_activity"
        / "story_interactions"
        / "story_likes.json"
    ).read_text()
)

INSTAGRAM_STORY_LIKES_V1_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "your_instagram_activity"
        / "story_interactions"
        / "story_likes.json"
    ).read_text()
)

INSTAGRAM_POST_COMMENTS_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "your_instagram_activity"
        / "comments"
        / "post_comments_1.json"
    ).read_text()
)

INSTAGRAM_REELS_COMMENTS_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "your_instagram_activity"
        / "comments"
        / "reels_comments.json"
    ).read_text()
)

INSTAGRAM_FOLLOWERS_JSON: list[dict] = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "connections"
        / "followers_and_following"
        / "followers_1.json"
    ).read_text()
)

INSTAGRAM_FOLLOWING_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "connections"
        / "followers_and_following"
        / "following.json"
    ).read_text()
)

INSTAGRAM_SAVED_POSTS_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR / "your_instagram_activity" / "saved" / "saved_posts.json"
    ).read_text()
)

INSTAGRAM_SAVED_COLLECTIONS_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "your_instagram_activity"
        / "saved"
        / "saved_collections.json"
    ).read_text()
)

INSTAGRAM_DM_INBOX_JSON: dict = json.loads(
    (
        ALICE_INSTAGRAM_DIR
        / "your_instagram_activity"
        / "messages"
        / "inbox"
        / "bobsmith_1234567890"
        / "message_1.json"
    ).read_text()
)
