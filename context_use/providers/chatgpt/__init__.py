from context_use.providers.chatgpt import (
    conversations,  # noqa: F401 — triggers declare_interaction
)
from context_use.providers.chatgpt.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(PROVIDER)

__all__ = ["PROVIDER"]
