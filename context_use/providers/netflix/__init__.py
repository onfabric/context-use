from context_use.providers.netflix import (
    indicated_preferences,
    messages_from_netflix,
    my_list,
    ratings,
    search_history,
    viewing_activity,
)
from context_use.providers.netflix.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[
        indicated_preferences,
        messages_from_netflix,
        my_list,
        ratings,
        search_history,
        viewing_activity,
    ],
)

__all__ = ["PROVIDER"]
