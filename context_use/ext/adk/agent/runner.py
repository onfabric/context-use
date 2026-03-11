from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from context_use.agent.backend import AgentBackend, AgentResult
from context_use.ext.adk.agent.agent import create_agent

if TYPE_CHECKING:
    from context_use.facade.core import ContextUse

logger = logging.getLogger(__name__)


async def _run_agent(
    ctx: ContextUse,
    model: LiteLlm,
    message: str,
) -> str:
    agent = create_agent(ctx, model=model)
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
                final_text = "\n".join(
                    part.text for part in event.content.parts if part.text
                )
            break

    logger.info("Personal agent complete (session=%s)", session_id)
    return final_text


class AdkAgentBackend(AgentBackend):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        api_base: str = "",
    ) -> None:
        kwargs: dict = {"model": model, "api_key": api_key}
        if api_base:
            kwargs["api_base"] = api_base
        self._model = LiteLlm(**kwargs)

    async def run(
        self,
        ctx: ContextUse,
        message: str,
    ) -> AgentResult:
        summary = await _run_agent(ctx, self._model, message)
        return AgentResult(summary=summary)
