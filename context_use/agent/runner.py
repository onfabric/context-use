from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

import context_use as _pkg
from context_use.agent.protocol import MemoryOperations
from context_use.agent.tools import make_agent_tools
from context_use.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_AGENT_NAME = "personal_memory_agent"
_USER_ID = "agent"
_SYSTEM_PROMPT_PATH = Path(_pkg.__file__).parent / "agent" / "system.md"


class AgentContentRole(StrEnum):
    """Should stay in sync with https://github.com/googleapis/python-genai/blob/07ae1b166c696a83697510ac51dbc880d1660fd0/google/genai/types.py#L2120"""

    USER = "user"
    MODEL = "model"


@dataclass
class AgentResult:
    summary: str


def _render_system_prompt(_ctx: Any) -> str:
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    return _SYSTEM_PROMPT_PATH.read_text().format(current_time=current_time)


def _handle_tool_error(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    error: Exception,
) -> dict[str, Any]:
    logger.warning("Tool error (tool=%s args=%s): %s", tool.name, args, error)
    return {"error": str(error)}


class AgentRunner:
    def __init__(
        self,
        ops: MemoryOperations,
        llm_client: BaseLLMClient,
    ) -> None:
        llm = LiteLlm(model=llm_client._model, api_key=llm_client._api_key)  # type: ignore[attr-defined]
        tools = make_agent_tools(ops)
        agent = LlmAgent(
            name=_AGENT_NAME,
            model=llm,
            instruction=_render_system_prompt,
            tools=tools,
            on_tool_error_callback=_handle_tool_error,
        )
        self._runner = Runner(
            agent=agent,
            app_name=_AGENT_NAME,
            session_service=InMemorySessionService(),
        )

    async def run(self, message: str) -> AgentResult:
        session_id = str(uuid.uuid4())
        await self._runner.session_service.create_session(
            app_name=_AGENT_NAME,
            user_id=_USER_ID,
            session_id=session_id,
        )
        logger.debug("Agent started (session=%s)", session_id)

        final_text = ""
        async for event in self._runner.run_async(
            user_id=_USER_ID,
            session_id=session_id,
            new_message=types.Content(
                role=AgentContentRole.USER,
                parts=[types.Part(text=message)],
            ),
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_text = "\n".join(
                        part.text for part in event.content.parts if part.text
                    )
                break

        logger.debug("Agent complete (session=%s)", session_id)
        return AgentResult(summary=final_text)
