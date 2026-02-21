from pathlib import Path

import pytest

from context_use import ContextUse
from context_use.etl.core.exceptions import (
    ArchiveProcessingError,
    UnsupportedProviderError,
)
from context_use.providers.registry import Provider
from tests.conftest import build_zip


class TestE2EErrors:
    async def test_bad_zip(self, ctx: ContextUse, tmp_path: Path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip file")

        with pytest.raises(ArchiveProcessingError):
            await ctx.process_archive(Provider.CHATGPT, str(bad))

    async def test_unsupported_provider(self, ctx: ContextUse, tmp_path: Path):
        dummy = tmp_path / "dummy.zip"
        data = build_zip({"file.txt": "hello"})
        dummy.write_bytes(data)

        with pytest.raises(UnsupportedProviderError):
            await ctx.process_archive("unknown_provider", str(dummy))  # pyright: ignore[reportArgumentType]

    async def test_empty_archive(self, ctx: ContextUse, tmp_path: Path):
        """An archive with no matching manifests should still succeed with 0 tasks."""
        empty_zip = tmp_path / "empty.zip"
        data = build_zip({"readme.txt": "nothing here"})
        empty_zip.write_bytes(data)

        result = await ctx.process_archive(Provider.CHATGPT, str(empty_zip))
        assert result.tasks_completed == 0
        assert result.threads_created == 0

    async def test_corrupt_json(self, ctx: ContextUse, tmp_path: Path):
        """Archive with a corrupt conversations.json should fail gracefully."""
        bad_json_zip = tmp_path / "bad_json.zip"
        data = build_zip({"conversations.json": "{not valid json]]]"})
        bad_json_zip.write_bytes(data)

        result = await ctx.process_archive(Provider.CHATGPT, str(bad_json_zip))
        # The task should fail but the archive should complete (with errors)
        assert result.tasks_failed == 1
        assert len(result.errors) > 0
