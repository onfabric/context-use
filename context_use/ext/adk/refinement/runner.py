# pyright: reportMissingImports=false
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import litellm

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
except ImportError as _exc:
    raise ImportError(
        "The adk extra is required for AdkRefinementBackend.\n"
        "Install it with: pip install context-use[adk]"
    ) from _exc

from context_use.ext.adk.refinement.agent import create_refinement_agent
from context_use.memories.refinement.backend import RefinementBackend, RefinementResult

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)

_MAX_LLM_CALLS = 50

_TRIGGER_MESSAGE = (
    "Review and curate all memories in the store. "
    "Identify and fix duplicate, overlapping, and low-quality memories: "
    "merge duplicates, split over-broad entries, correct wrong date ranges, "
    "and archive superseded content. "
    "Return a structured summary of every change you made."
)


class _RefinementRunner(Runner):
    """Internal ADK Runner — one instance per refinement run."""

    def __init__(
        self,
        store: Store,
        llm_client: BaseLLMClient,
        model: str,
    ) -> None:
        agent = create_refinement_agent(store, llm_client, model=model)
        super().__init__(
            agent=agent,
            app_name=agent.name,
            session_service=InMemorySessionService(),
        )

    async def run_refinement(self) -> str:
        session_id = str(uuid.uuid4())
        await self.session_service.create_session(
            app_name=self.app_name,
            user_id="refinement",
            session_id=session_id,
        )
        logger.info("Refinement agent started (session=%s)", session_id)

        final_text = ""
        async for event in self.run_async(
            user_id="refinement",
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=_TRIGGER_MESSAGE)],
            ),
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_text = event.content.parts[0].text or ""
                break

        logger.info("Refinement agent complete (session=%s)", session_id)
        return final_text


class AdkRefinementBackend(RefinementBackend):
    """ADK-based refinement backend. Runs a multi-turn LlmAgent.

    The agent explores the memory store across multiple tool calls, then
    executes merges, splits, date corrections, and archives autonomously.

    Requires the ``adk`` extra::

        pip install context-use[adk]
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
    ) -> None:
        """
        Args:
            api_key: OpenAI (or compatible) API key. Set globally on
                     litellm so the ``LiteLlm`` model wrapper picks it up.
            model:   LiteLLM model string.
        """
        litellm.openai_key = api_key
        self._model = model

    async def run(self, store: Store, llm_client: BaseLLMClient) -> RefinementResult:
        runner = _RefinementRunner(store, llm_client, self._model)
        summary = await runner.run_refinement()
        return RefinementResult(summary=summary)
