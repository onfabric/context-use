from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

ALICE_CHATGPT_DIR = FIXTURES_DIR / "users" / "alice" / "chatgpt" / "v1"
ALICE_GOOGLE_DIR = FIXTURES_DIR / "users" / "alice" / "google" / "v1"
ALICE_INSTAGRAM_DIR = FIXTURES_DIR / "users" / "alice" / "instagram" / "v1"

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


def build_zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def zip_fixture_dir(fixture_dir: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(fixture_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(fixture_dir))
    return dest


@pytest.fixture()
def chatgpt_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_CHATGPT_DIR, tmp_path / "chatgpt-export.zip")


@pytest.fixture()
def google_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_GOOGLE_DIR, tmp_path / "google-export.zip")


@pytest.fixture()
def instagram_zip(tmp_path: Path) -> Path:
    return zip_fixture_dir(ALICE_INSTAGRAM_DIR, tmp_path / "instagram-export.zip")
