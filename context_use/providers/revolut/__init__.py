from context_use.providers.registry import register_provider
from context_use.providers.revolut import transactions

PROVIDER = "revolut"

register_provider(PROVIDER, modules=[transactions])

__all__ = ["PROVIDER"]
