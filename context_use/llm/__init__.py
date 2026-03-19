from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.llm.base import (
        BaseLLMClient,
        BatchResults,
        EmbedBatchResults,
        EmbedItem,
        PromptItem,
    )

__all__ = [
    "BaseLLMClient",
    "BatchResults",
    "EmbedBatchResults",
    "EmbedItem",
    "PromptItem",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from context_use.llm.base import (
        BaseLLMClient,
        BatchResults,
        EmbedBatchResults,
        EmbedItem,
        PromptItem,
    )

    value: Any = {
        "BaseLLMClient": BaseLLMClient,
        "BatchResults": BatchResults,
        "EmbedBatchResults": EmbedBatchResults,
        "EmbedItem": EmbedItem,
        "PromptItem": PromptItem,
    }[name]

    globals()[name] = value
    return value
