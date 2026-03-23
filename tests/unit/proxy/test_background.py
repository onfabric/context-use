from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from context_use.proxy.handler import ContextProxy


def _mock_ctx(thread_ids: list[str] | None = None) -> AsyncMock:
    ctx = AsyncMock()
    ctx.insert_threads = AsyncMock(
        return_value=thread_ids if thread_ids is not None else ["tid-1"]
    )
    ctx.count_memories = AsyncMock(return_value=5)
    return ctx


def _make_test_callback() -> tuple[MagicMock, MagicMock]:
    process_called = MagicMock()

    def callback(ctx: object, thread_ids: list[str]) -> None:
        async def _run() -> None:
            await ctx.generate_memories_from_threads(thread_ids)  # type: ignore[union-attr]
            process_called()

        asyncio.create_task(_run())

    return MagicMock(side_effect=callback), process_called


class TestScheduleEndToEnd:
    async def test_store_and_schedule_calls_callback(self) -> None:
        ctx = _mock_ctx()
        callback, process_called = _make_test_callback()
        proxy = ContextProxy(ctx, post_response_callback=callback)

        await proxy._store_and_schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id=None,
        )

        await asyncio.sleep(0.1)
        callback.assert_called_once()
        process_called.assert_called_once()

    async def test_no_callback_still_inserts_threads(self) -> None:
        ctx = _mock_ctx()
        proxy = ContextProxy(ctx)

        await proxy._store_and_schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id=None,
        )

        ctx.insert_threads.assert_awaited_once()
        ctx.generate_memories_from_threads.assert_not_awaited()

    async def test_callback_receives_ctx_thread_ids_and_session(self) -> None:
        ctx = _mock_ctx(thread_ids=["tid-42"])
        custom = MagicMock()
        proxy = ContextProxy(ctx, post_response_callback=custom)

        await proxy._store_and_schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id="sess-1",
        )

        custom.assert_called_once_with(ctx, ["tid-42"])

    async def test_all_duplicates_skips_callback(self) -> None:
        ctx = _mock_ctx(thread_ids=[])
        custom = MagicMock()
        proxy = ContextProxy(ctx, post_response_callback=custom)

        await proxy._store_and_schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id=None,
        )

        ctx.insert_threads.assert_awaited_once()
        custom.assert_not_called()
