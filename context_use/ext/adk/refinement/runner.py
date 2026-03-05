# pyright: reportMissingImports=false
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

try:
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
except ImportError as _exc:
    raise ImportError(
        "The adk extra is required for AdkRefinementBackend.\n"
        "Install it with: uv sync --extra adk"
    ) from _exc

from context_use.ext.adk.refinement.agent import create_refinement_agent
from context_use.memories.refinement.backend import RefinementBackend, RefinementResult

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)

_TRIGGER_MESSAGE = (
    "Investigate the memory store and synthesise pattern memories. "
    "For each topic, search broadly, follow the threads that emerge, "
    "and keep digging until you have converged on everything the store holds "
    "for that area of the user's life. "
    "Then synthesise a pattern memory capturing what is consistently true. "
    "Repeat for at least 6–8 meaningfully different topics. "
    "Do not archive the source event memories — patterns are additive. "
    "Return a structured summary of every pattern created or updated."
)


async def _run_refinement(
    store: Store,
    llm_client: BaseLLMClient,
    model: LiteLlm,
) -> str:
    agent = create_refinement_agent(store, llm_client, model=model)
    runner = Runner(
        agent=agent,
        app_name=agent.name,
        session_service=InMemorySessionService(),
    )

    session_id = str(uuid.uuid4())
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="refinement",
        session_id=session_id,
    )
    logger.info("Refinement agent started (session=%s)", session_id)

    final_text = ""
    async for event in runner.run_async(
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

        uv sync --extra adk
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
    ) -> None:
        """
        Args:
            api_key: OpenAI (or compatible) API key.
            model:   LiteLLM model string.
        """
        self._model = LiteLlm(model=model, api_key=api_key)

    async def run(self, store: Store, llm_client: BaseLLMClient) -> RefinementResult:
        summary = await _run_refinement(store, llm_client, self._model)
        return RefinementResult(summary=summary)
