from context_use.providers.bank import amex, barclays, revolut
from context_use.providers.bank.schemas import PROVIDER
from context_use.providers.registry import register_provider

register_provider(
    PROVIDER,
    modules=[revolut, amex, barclays],
)

__all__ = ["PROVIDER"]
