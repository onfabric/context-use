from context_use.providers.chatgpt import (
    conversations,  # noqa: F401 — triggers register_interaction
)
from context_use.providers.registry import build_and_register_provider

PROVIDER = "chatgpt"
build_and_register_provider(PROVIDER)

__all__ = ["PROVIDER"]
