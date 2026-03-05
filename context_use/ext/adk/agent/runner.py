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
        "The adk extra is required for AdkAgentBackend.\n"
        "Install it with: uv sync --extra adk"
    ) from _exc

from context_use.ext.adk.agent.agent import create_agent
from context_use.memories.agent.backend import AgentBackend, AgentResult

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


async def _run_agent(
    store: Store,
    llm_client: BaseLLMClient,
    model: LiteLlm,
    message: str,
) -> str:
    agent = create_agent(store, llm_client, model=model)
    runner = Runner(
        agent=agent,
        app_name=agent.name,
        session_service=InMemorySessionService(),
    )

    session_id = str(uuid.uuid4())
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="agent",
        session_id=session_id,
    )
    logger.info("Personal agent started (session=%s)", session_id)

    final_text = ""
    async for event in runner.run_async(
        user_id="agent",
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ),
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_text = "".join(
                    part.text for part in event.content.parts if part.text
                )
            break

    logger.info("Personal agent complete (session=%s)", session_id)
    return final_text


class AdkAgentBackend(AgentBackend):
    """ADK-based personal agent backend.

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

    async def run(
        self,
        store: Store,
        llm_client: BaseLLMClient,
        message: str,
    ) -> AgentResult:
        summary = await _run_agent(store, llm_client, self._model, message)
        return AgentResult(summary=summary)
