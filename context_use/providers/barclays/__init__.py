from context_use.providers.barclays import transactions
from context_use.providers.registry import register_provider

PROVIDER = "barclays"

register_provider(PROVIDER, modules=[transactions])

__all__ = ["PROVIDER"]
