from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from context_use.etl.core.etl import (
    ExtractionStrategy,
    OrchestrationStrategy,
    TransformStrategy,
)
from context_use.etl.providers.chatgpt.conversations import (
    ChatGPTConversationsExtractionStrategy,
    ChatGPTConversationsTransformStrategy,
)
from context_use.etl.providers.chatgpt.orchestration import ChatGPTOrchestrationStrategy
from context_use.etl.providers.instagram.media import (
    InstagramReelsExtractionStrategy,
    InstagramReelsTransformStrategy,
    InstagramStoriesExtractionStrategy,
    InstagramStoriesTransformStrategy,
)
from context_use.etl.providers.instagram.orchestration import (
    InstagramOrchestrationStrategy,
)


class Provider(StrEnum):
    CHATGPT = "chatgpt"
    INSTAGRAM = "instagram"


@dataclass
class InteractionTypeConfig:
    extraction: type[ExtractionStrategy]
    transform: type[TransformStrategy]


@dataclass
class ProviderConfig:
    orchestration: type[OrchestrationStrategy]
    interaction_types: dict[str, InteractionTypeConfig]


PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: ProviderConfig(
        orchestration=ChatGPTOrchestrationStrategy,
        interaction_types={
            "chatgpt_conversations": InteractionTypeConfig(
                extraction=ChatGPTConversationsExtractionStrategy,
                transform=ChatGPTConversationsTransformStrategy,
            ),
        },
    ),
    Provider.INSTAGRAM: ProviderConfig(
        orchestration=InstagramOrchestrationStrategy,
        interaction_types={
            "instagram_stories": InteractionTypeConfig(
                extraction=InstagramStoriesExtractionStrategy,
                transform=InstagramStoriesTransformStrategy,
            ),
            "instagram_reels": InteractionTypeConfig(
                extraction=InstagramReelsExtractionStrategy,
                transform=InstagramReelsTransformStrategy,
            ),
        },
    ),
}


def get_provider_config(provider: Provider) -> ProviderConfig:
    """Look up the provider config. Raises ``KeyError`` for unknown providers."""
    return PROVIDER_REGISTRY[provider]
