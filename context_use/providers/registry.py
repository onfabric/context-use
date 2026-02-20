from __future__ import annotations

from enum import StrEnum

from context_use.memories.config import MemoryConfig
from context_use.providers.chatgpt import PROVIDER_CONFIG as _CHATGPT_CONFIG
from context_use.providers.instagram import PROVIDER_CONFIG as _INSTAGRAM_CONFIG
from context_use.providers.types import (  # noqa: F401 — re-exported
    InteractionConfig,
    ProviderConfig,
)


class Provider(StrEnum):
    CHATGPT = "chatgpt"
    INSTAGRAM = "instagram"


PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: _CHATGPT_CONFIG,
    Provider.INSTAGRAM: _INSTAGRAM_CONFIG,
}


def get_provider_config(provider: Provider) -> ProviderConfig:
    """Look up the provider config. Raises ``KeyError`` for unknown providers."""
    return PROVIDER_REGISTRY[provider]


def get_memory_config(interaction_type: str) -> MemoryConfig:
    """Look up memory config across all providers.

    Raises ``KeyError`` if no memory config has been registered for the
    given interaction type.
    """
    for config in PROVIDER_REGISTRY.values():
        try:
            return config.get_memory_config(interaction_type)
        except KeyError:
            continue
    raise KeyError(f"No memory config for interaction_type={interaction_type!r}")
