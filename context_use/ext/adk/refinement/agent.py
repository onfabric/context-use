# pyright: reportMissingImports=false
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext
except ImportError as _exc:
    raise ImportError(
        "The adk extra is required for the refinement agent.\n"
        "Install it with: uv sync --extra adk"
    ) from _exc

import context_use as _pkg

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(_pkg.__file__).parent / "memories" / "refinement" / "agent_prompt.md"
)


def _render_instruction(_ctx: Any) -> str:
    """Render the agent prompt with the current time injected."""
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    return _PROMPT_PATH.read_text().format(current_time=current_time)


def _handle_tool_error(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    error: Exception,
) -> dict[str, Any]:
    """Return the error message to the LLM so it can self-correct."""
    logger.warning("Tool error (tool=%s args=%s): %s", tool.name, args, error)
    return {"error": str(error)}


def create_refinement_agent(
    store: Store,
    llm_client: BaseLLMClient,
    *,
    model: LiteLlm,
) -> LlmAgent:
    """Create a memory refinement LlmAgent bound to *store* and *llm_client*.

    A fresh agent is created per invocation so the tool closures are always
    bound to the correct store instance (mirrors the ``create_server`` pattern
    in ``ext/mcp_use/server.py``).

    Args:
        store:      The Store instance to read from and write to.
        llm_client: Used by the search tool to embed text queries.
        model:      Configured ``LiteLlm`` instance.
    """
    from context_use.memories.refinement.tools import make_refinement_tools

    tools = make_refinement_tools(store, llm_client)

    return LlmAgent(
        name="memory_refinement_agent",
        model=model,
        instruction=_render_instruction,
        tools=tools,
        on_tool_error_callback=_handle_tool_error,
    )
