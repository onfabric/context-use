from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from context_use.agent.runner import AgentResult
from context_use.proxy.background import BackgroundMemoryProcessor


def _make_processor(
    *,
    max_concurrent: int = 3,
) -> tuple[BackgroundMemoryProcessor, AsyncMock]:
    ctx = AsyncMock()
    ctx.run_agent = AsyncMock(return_value=AgentResult(summary="done"))
    ctx.insert_threads = AsyncMock(return_value=1)

    processor = BackgroundMemoryProcessor(ctx, max_concurrent=max_concurrent)
    return processor, ctx


class TestBackgroundMemoryProcessor:
    async def test_schedule_stores_threads_and_runs_agent(self) -> None:
        processor, ctx = _make_processor()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        processor.schedule(messages, session_id="sess-1")

        await asyncio.sleep(0.1)
        while processor._tasks:
            await asyncio.sleep(0.05)

        ctx.insert_threads.assert_awaited_once()
        ctx.run_agent.assert_awaited_once()

        call_args = ctx.run_agent.call_args
        prompt = call_args.args[0]
        assert "Hello" in prompt
        assert "Hi there" in prompt

    async def test_schedule_with_empty_messages_skips_agent(self) -> None:
        processor, ctx = _make_processor()

        messages = [{"role": "system", "content": "Be helpful"}]
        processor.schedule(messages)

        await asyncio.sleep(0.1)
        while processor._tasks:
            await asyncio.sleep(0.05)

        ctx.insert_threads.assert_not_awaited()
        ctx.run_agent.assert_not_awaited()

    async def test_agent_error_is_logged_not_raised(self) -> None:
        processor, ctx = _make_processor()
        ctx.run_agent.side_effect = RuntimeError("LLM down")

        messages = [{"role": "user", "content": "Hi"}]
        processor.schedule(messages)

        await asyncio.sleep(0.1)
        while processor._tasks:
            await asyncio.sleep(0.05)

        ctx.insert_threads.assert_awaited_once()

    async def test_semaphore_limits_concurrency(self) -> None:
        processor, ctx = _make_processor(max_concurrent=1)

        call_count = 0
        max_concurrent_seen = 0
        current_concurrent = 0

        async def tracked_run(*args: object, **kwargs: object) -> AgentResult:
            nonlocal call_count, max_concurrent_seen, current_concurrent
            current_concurrent += 1
            max_concurrent_seen = max(max_concurrent_seen, current_concurrent)
            call_count += 1
            await asyncio.sleep(0.05)
            current_concurrent -= 1
            return AgentResult(summary="done")

        ctx.run_agent = tracked_run

        for _ in range(3):
            processor.schedule([{"role": "user", "content": "Hi"}])

        await asyncio.sleep(0.5)
        while processor._tasks:
            await asyncio.sleep(0.05)

        assert call_count == 3
        assert max_concurrent_seen == 1

    async def test_task_cleanup(self) -> None:
        processor, ctx = _make_processor()

        processor.schedule([{"role": "user", "content": "Hi"}])
        assert len(processor._tasks) >= 0

        await asyncio.sleep(0.2)
        while processor._tasks:
            await asyncio.sleep(0.05)

        assert len(processor._tasks) == 0

    async def test_session_id_passed_to_thread_builder(self) -> None:
        processor, ctx = _make_processor()

        with patch(
            "context_use.proxy.background.messages_to_thread_rows"
        ) as mock_build:
            mock_build.return_value = []
            processor.schedule(
                [{"role": "user", "content": "Hi"}], session_id="my-session"
            )

            await asyncio.sleep(0.1)
            while processor._tasks:
                await asyncio.sleep(0.05)

            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args
            assert call_kwargs.kwargs["session_id"] == "my-session"
