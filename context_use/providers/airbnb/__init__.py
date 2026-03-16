from context_use.providers.airbnb import (
    messages,
    reservations,
    reviews,
    search_history,
    wishlists,
)
from context_use.providers.airbnb.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[messages, reservations, reviews, search_history, wishlists],
)

__all__ = ["PROVIDER"]
