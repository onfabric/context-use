from context_use.providers.registry import register_provider
from context_use.providers.telegram import conversations
from context_use.providers.telegram.conversations.pipe import PROVIDER

register_provider(PROVIDER, modules=[conversations])

__all__ = ["PROVIDER"]
