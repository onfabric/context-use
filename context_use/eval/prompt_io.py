from __future__ import annotations

from pathlib import Path

from context_use.memories.prompt.conversation import (
    AGENT_PROMPT_OVERRIDE,
    OUTPUT_FORMAT,
)


def body_to_template(body: str) -> str:
    return body.rstrip() + "\n\n{{CONTEXT}}{{TRANSCRIPT}}\n\n" + OUTPUT_FORMAT


def save_prompt_body(body: str) -> Path:
    template = body_to_template(body)
    AGENT_PROMPT_OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PROMPT_OVERRIDE.write_text(template)
    return AGENT_PROMPT_OVERRIDE


def clear_prompt_override() -> bool:
    if AGENT_PROMPT_OVERRIDE.is_file():
        AGENT_PROMPT_OVERRIDE.unlink()
        return True
    return False
