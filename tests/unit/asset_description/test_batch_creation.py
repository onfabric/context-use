from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from context_use.core import ContextUse
from context_use.models.thread import Thread


def _make_thread(
    *,
    thread_id: str = "t1",
    asset_uri: str | None = "archive/pic.jpg",
) -> Thread:
    return Thread(
        id=thread_id,
        unique_key=f"uk-{thread_id}",
        provider="Instagram",
        interaction_type="instagram_posts",
        payload={"type": "Create", "fibre_kind": "Create", "object": {"type": "Image"}},
        version="1.1.0",
        asat=datetime(2025, 1, 1, tzinfo=UTC),
        asset_uri=asset_uri,
    )


def _make_ctx(
    *,
    threads: list[Thread],
    media_prefixes: tuple[str, ...] = ("image/",),
) -> ContextUse:
    store = AsyncMock()
    store.get_unprocessed_threads = AsyncMock(return_value=threads)
    store.create_batch = AsyncMock(side_effect=lambda b, _groups: b)

    llm_client = MagicMock()
    type(llm_client).supported_media_prefixes = PropertyMock(
        return_value=media_prefixes
    )

    storage = MagicMock()

    ctx = object.__new__(ContextUse)
    ctx._store = store
    ctx._llm_client = llm_client
    ctx._storage = storage
    return ctx


@pytest.fixture(autouse=True)
def _register_providers() -> None:
    import context_use.providers  # noqa: F401


class TestCreateAssetDescriptionBatches:
    @pytest.mark.asyncio
    async def test_filters_video_with_default_prefixes(self) -> None:
        threads = [
            _make_thread(thread_id="img", asset_uri="archive/pic.jpg"),
            _make_thread(thread_id="mp4", asset_uri="archive/clip.mp4"),
            _make_thread(thread_id="png", asset_uri="archive/shot.png"),
        ]
        ctx = _make_ctx(threads=threads)

        with patch(
            "context_use.asset_description.factory.AssetDescriptionBatchFactory.create_batches",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_create:
            await ctx.create_asset_description_batches()
            groups = mock_create.call_args[0][0]

        group_ids = [g.group_id for g in groups]
        assert "img" in group_ids
        assert "png" in group_ids
        assert "mp4" not in group_ids

    @pytest.mark.asyncio
    async def test_includes_video_when_client_supports_it(self) -> None:
        threads = [
            _make_thread(thread_id="img", asset_uri="archive/pic.jpg"),
            _make_thread(thread_id="mp4", asset_uri="archive/clip.mp4"),
        ]
        ctx = _make_ctx(threads=threads, media_prefixes=("image/", "video/"))

        with patch(
            "context_use.asset_description.factory.AssetDescriptionBatchFactory.create_batches",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_create:
            await ctx.create_asset_description_batches()
            groups = mock_create.call_args[0][0]

        group_ids = [g.group_id for g in groups]
        assert "img" in group_ids
        assert "mp4" in group_ids

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_supported_media(self) -> None:
        threads = [
            _make_thread(thread_id="mp4", asset_uri="archive/clip.mp4"),
        ]
        ctx = _make_ctx(threads=threads)

        batches = await ctx.create_asset_description_batches()
        assert batches == []

    @pytest.mark.asyncio
    async def test_excludes_threads_without_asset_uri(self) -> None:
        threads = [
            _make_thread(thread_id="no-asset", asset_uri=None),
            _make_thread(thread_id="img", asset_uri="archive/pic.jpg"),
        ]
        ctx = _make_ctx(threads=threads)

        with patch(
            "context_use.asset_description.factory.AssetDescriptionBatchFactory.create_batches",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_create:
            await ctx.create_asset_description_batches()
            groups = mock_create.call_args[0][0]

        group_ids = [g.group_id for g in groups]
        assert group_ids == ["img"]

    @pytest.mark.asyncio
    async def test_forwards_task_id_to_store(self) -> None:
        ctx = _make_ctx(threads=[])
        await ctx.create_asset_description_batches(task_id="task-42")

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["task_id"] == "task-42"

    @pytest.mark.asyncio
    async def test_task_id_defaults_to_none(self) -> None:
        ctx = _make_ctx(threads=[])
        await ctx.create_asset_description_batches()

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        assert mock.call_args.kwargs["task_id"] is None
