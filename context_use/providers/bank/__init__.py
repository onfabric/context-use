from context_use.providers.bank import generic_pipe  # noqa: F401
from context_use.providers.registry import register_provider

register_provider("bank", modules=[generic_pipe])
