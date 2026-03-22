from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from context_use.proxy.handler import ContextProxy


def _mock_ctx() -> AsyncMock:
    ctx = AsyncMock()
    ctx.count_memories = AsyncMock(return_value=5)
    return ctx


def _make_test_callback() -> tuple[MagicMock, MagicMock]:
    process_called = MagicMock()

    def callback(
        ctx: object, messages: list[dict[str, Any]], session_id: str | None
    ) -> None:
        async def _run() -> None:
            await ctx.generate_memories_from_messages(messages, session_id=session_id)  # type: ignore[union-attr]
            process_called()

        asyncio.create_task(_run())

    return MagicMock(side_effect=callback), process_called


class TestScheduleEndToEnd:
    async def test_schedule_calls_callback(self) -> None:
        ctx = _mock_ctx()
        callback, process_called = _make_test_callback()
        proxy = ContextProxy(ctx, post_response_callback=callback)

        proxy._schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id=None,
        )

        await asyncio.sleep(0.1)
        callback.assert_called_once()
        process_called.assert_called_once()

    async def test_no_callback_is_noop(self) -> None:
        ctx = _mock_ctx()
        proxy = ContextProxy(ctx)

        proxy._schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id=None,
        )

        await asyncio.sleep(0.1)
        ctx.generate_memories_from_messages.assert_not_awaited()

    async def test_callback_receives_ctx_messages_and_session(self) -> None:
        ctx = _mock_ctx()
        custom = MagicMock()
        proxy = ContextProxy(ctx, post_response_callback=custom)

        proxy._schedule(
            [{"role": "user", "content": "Hi"}],
            "Hello!",
            session_id="sess-1",
        )

        custom.assert_called_once_with(
            ctx,
            [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "sess-1",
        )
