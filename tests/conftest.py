import io
import json
import zipfile
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALICE_CHATGPT_DIR = FIXTURES_DIR / "users" / "alice" / "chatgpt" / "v1"
ALICE_CLAUDE_DIR = FIXTURES_DIR / "users" / "alice" / "claude" / "v1"
ALICE_GOOGLE_DIR = FIXTURES_DIR / "users" / "alice" / "google" / "v1"
ALICE_INSTAGRAM_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v1"
ALICE_INSTAGRAM_V0_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v0"


CHATGPT_CONVERSATIONS: list[dict] = json.loads(
    (ALICE_CHATGPT_DIR / "conversations.json").read_text()
)

CLAUDE_CONVERSATIONS: list[dict] = json.loads(
    (ALICE_CLAUDE_DIR / "conversations.json").read_text()
)


GOOGLE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "Search" / "MyActivity.json"
    ).read_text()
)

GOOGLE_VIDEO_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Video Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_IMAGE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Image Search"
        / "MyActivity.json"
    ).read_text()
)


GOOGLE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "Search" / "MyActivity.json"
    ).read_text()
)

GOOGLE_VIDEO_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Video Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_IMAGE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Image Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_YOUTUBE_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "YouTube" / "MyActivity.json"
    ).read_text()
)


GOOGLE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "Search" / "MyActivity.json"
    ).read_text()
)

GOOGLE_VIDEO_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Video Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_IMAGE_SEARCH_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Image Search"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_SHOPPING_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Shopping"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_DISCOVER_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Discover"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_LENS_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR
        / "Portability"
        / "My Activity"
        / "Google Lens"
        / "MyActivity.json"
    ).read_text()
)

GOOGLE_YOUTUBE_JSON: list[dict] = json.loads(
    (
        ALICE_GOOGLE_DIR / "Portability" / "My Activity" / "YouTube" / "MyActivity.json"
    ).read_text()
)


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


def build_zip(files: dict[str, bytes | str]) -> bytes:
    """Create an in-memory zip archive from a dict of {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def zip_fixture_dir(fixture_dir: Path, dest: Path) -> Path:
    """Zip an entire fixture directory tree into *dest*."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(fixture_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(fixture_dir))
    return dest


@pytest.fixture()
def chatgpt_zip(tmp_path: Path) -> Path:
    """Zip alice's synthetic ChatGPT archive into a temp file."""
    return zip_fixture_dir(ALICE_CHATGPT_DIR, tmp_path / "chatgpt-export.zip")


@pytest.fixture()
def google_zip(tmp_path: Path) -> Path:
    """Zip alice's synthetic Google Takeout archive into a temp file."""
    return zip_fixture_dir(ALICE_GOOGLE_DIR, tmp_path / "google-export.zip")


@pytest.fixture()
def instagram_zip(tmp_path: Path) -> Path:
    """Zip alice's synthetic Instagram archive into a temp file."""
    return zip_fixture_dir(ALICE_INSTAGRAM_DIR, tmp_path / "instagram-export.zip")
