from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from context_use.agent.skill import make_process_thread_skill
from context_use.memories.prompt.conversation import format_transcript
from context_use.models.thread import Thread
from context_use.proxy.threads import messages_to_thread_rows

if TYPE_CHECKING:
    from typing import Any

    from context_use.agent.backend import AgentBackend
    from context_use.facade.core import ContextUse

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_AGENTS = 3
# TODO: if proxy traffic becomes high-volume, consider a persistent queue
# or backpressure mechanism instead of unbounded in-memory tasks.


class BackgroundMemoryProcessor:
    def __init__(
        self,
        ctx: ContextUse,
        backend: AgentBackend,
        *,
        max_concurrent: int = _MAX_CONCURRENT_AGENTS,
    ) -> None:
        self._ctx = ctx
        self._backend = backend
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._process(messages, session_id=session_id),
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> None:
        async with self._semaphore:
            try:
                threads = await self._store_threads(messages, session_id=session_id)
                if not threads:
                    return
                await self._run_agent(threads)
            except Exception:
                logger.error("Background memory processing failed", exc_info=True)

    async def _store_threads(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str | None = None,
    ) -> list[Thread]:
        rows = messages_to_thread_rows(messages, session_id=session_id)
        if not rows:
            return []

        await self._ctx.insert_threads(rows)
        logger.info("Threads created: n=%d session=%s", len(rows), session_id or "-")

        return [
            Thread(
                unique_key=r.unique_key,
                provider=r.provider,
                interaction_type=r.interaction_type,
                preview=r.preview,
                payload=r.payload,
                version=r.version,
                asat=r.asat,
            )
            for r in rows
        ]

    async def _run_agent(self, threads: list[Thread]) -> None:
        transcript = format_transcript(threads)
        skill = make_process_thread_skill(transcript)
        logger.info("Memory generation started: threads=%d", len(threads))
        result = await self._ctx.run_agent(self._backend, skill.prompt)
        logger.info("Memory generation finished: %s", result.summary)
