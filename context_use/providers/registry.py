from __future__ import annotations

from collections import defaultdict

from context_use.memories.config import MemoryConfig
from context_use.providers.types import InteractionConfig, ProviderConfig

_provider_registry: dict[str, ProviderConfig] = {}
_interactions_by_provider: dict[str, list[InteractionConfig]] = defaultdict(list)


def register_interaction(config: InteractionConfig) -> None:
    """Register an :class:`InteractionConfig`.

    Call this at module level in a pipe module. The provider package
    ``__init__.py`` is responsible for importing the module so that the
    registration fires at import time.

    Example::

        # providers/instagram/media.py
        from context_use.providers.registry import register_interaction

        register_interaction(
            InteractionConfig(pipe=InstagramStoriesPipe, memory=_MEDIA_MEMORY_CONFIG)
        )
    """
    _interactions_by_provider[config.pipe.provider].append(config)


def build_and_register_provider(name: str) -> None:
    """Build and register a :class:`ProviderConfig` for *name*.

    Call this once in a provider package ``__init__.py``, *after* importing all
    pipe modules (so their :func:`register_interaction` calls have already
    fired).

    Example::

        # providers/instagram/__init__.py
        from context_use.providers.instagram import (
            comments, connections, likes, media, ...  # triggers register_interaction
        )
        from context_use.providers.registry import build_and_register_provider

        build_and_register_provider(PROVIDER)
    """
    _provider_registry[name] = ProviderConfig(
        interactions=list(_interactions_by_provider.get(name, []))
    )


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return list(_provider_registry.keys())


def get_provider_config(provider: str) -> ProviderConfig:
    """Look up the provider config. Raises ``KeyError`` for unknown providers."""
    return _provider_registry[provider]


def get_memory_config(interaction_type: str) -> MemoryConfig:
    """Look up memory config across all providers.

    Raises ``KeyError`` if no memory config has been registered for the
    given interaction type.
    """
    for config in _provider_registry.values():
        try:
            return config.get_memory_config(interaction_type)
        except KeyError:
            continue
    raise KeyError(f"No memory config for interaction_type={interaction_type!r}")


def get_memory_interaction_types() -> list[str]:
    """Return all interaction types that have a memory config registered."""
    return [
        ic.pipe.interaction_type
        for config in _provider_registry.values()
        for ic in config.interactions
        if ic.memory is not None
    ]
