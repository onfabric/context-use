from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from context_use.core import ContextUse


def _make_ctx() -> ContextUse:
    store = AsyncMock()
    store.get_unprocessed_threads = AsyncMock(return_value=[])

    llm_client = MagicMock()
    storage = MagicMock()

    ctx = object.__new__(ContextUse)
    ctx._store = store
    ctx._llm_client = llm_client
    ctx._storage = storage
    return ctx


@pytest.fixture(autouse=True)
def _register_providers() -> None:
    import context_use.providers  # noqa: F401


class TestCreateMemoryBatches:
    @pytest.mark.asyncio
    async def test_forwards_task_id_to_store(self) -> None:
        ctx = _make_ctx()
        await ctx.create_memory_batches(task_id="task-42")

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["task_id"] == "task-42"

    @pytest.mark.asyncio
    async def test_task_id_defaults_to_none(self) -> None:
        ctx = _make_ctx()
        await ctx.create_memory_batches()

        mock: AsyncMock = ctx._store.get_unprocessed_threads  # type: ignore[assignment]
        assert mock.call_args.kwargs["task_id"] is None
