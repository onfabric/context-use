from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from context_use.etl.core.etl import (
    ExtractionStrategy,
    OrchestrationStrategy,
    TransformStrategy,
)
from context_use.etl.core.pipe import Pipe
from context_use.etl.providers.chatgpt.conversations import (
    ChatGPTConversationsPipe,
)
from context_use.etl.providers.chatgpt.orchestration import ChatGPTOrchestrationStrategy
from context_use.etl.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)
from context_use.etl.providers.instagram.orchestration import (
    InstagramOrchestrationStrategy,
)


class Provider(StrEnum):
    CHATGPT = "chatgpt"
    INSTAGRAM = "instagram"


@dataclass
class InteractionTypeConfig:
    extraction: type[ExtractionStrategy] | None = None
    transform: type[TransformStrategy] | None = None
    pipe: type[Pipe] | None = None


@dataclass
class ProviderConfig:
    orchestration: type[OrchestrationStrategy]
    interaction_types: dict[str, InteractionTypeConfig]


PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: ProviderConfig(
        orchestration=ChatGPTOrchestrationStrategy,
        interaction_types={
            "chatgpt_conversations": InteractionTypeConfig(
                pipe=ChatGPTConversationsPipe,
            ),
        },
    ),
    Provider.INSTAGRAM: ProviderConfig(
        orchestration=InstagramOrchestrationStrategy,
        interaction_types={
            "instagram_stories": InteractionTypeConfig(
                pipe=InstagramStoriesPipe,
            ),
            "instagram_reels": InteractionTypeConfig(
                pipe=InstagramReelsPipe,
            ),
        },
    ),
}


def get_provider_config(provider: Provider) -> ProviderConfig:
    """Look up the provider config. Raises ``KeyError`` for unknown providers."""
    return PROVIDER_REGISTRY[provider]
