from context_use.providers.google import search, youtube
from context_use.providers.google.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[search, youtube],
)

__all__ = ["PROVIDER"]
