from context_use.providers.google import discover, lens, search, shopping, youtube
from context_use.providers.google.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[discover, lens, search, shopping, youtube],
)

__all__ = ["PROVIDER"]
