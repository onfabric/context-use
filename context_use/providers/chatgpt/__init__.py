from context_use.providers.chatgpt.conversations import (
    INTERACTION_CONFIG as _CONVERSATIONS_CONFIG,
)
from context_use.providers.chatgpt.conversations import (
    ChatGPTConversationsPipe,
)
from context_use.providers.chatgpt.schemas import ChatGPTConversationRecord
from context_use.providers.types import ProviderConfig

PROVIDER_CONFIG = ProviderConfig(interactions=[_CONVERSATIONS_CONFIG])

__all__ = [
    "ChatGPTConversationRecord",
    "ChatGPTConversationsPipe",
    "PROVIDER_CONFIG",
]
