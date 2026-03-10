from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from context_use.llm.base import (
        BaseLLMClient,
        BatchResults,
        EmbedBatchResults,
        EmbedItem,
        PromptItem,
    )
    from context_use.llm.litellm import (
        LiteLLMBatchClient,
        LiteLLMSyncClient,
    )
    from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

__all__ = [
    "BaseLLMClient",
    "BatchResults",
    "EmbedBatchResults",
    "EmbedItem",
    "LiteLLMBatchClient",
    "LiteLLMSyncClient",
    "OpenAIEmbeddingModel",
    "OpenAIModel",
    "PromptItem",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    if name in {
        "BaseLLMClient",
        "BatchResults",
        "EmbedBatchResults",
        "EmbedItem",
        "PromptItem",
    }:
        from context_use.llm.base import (
            BaseLLMClient,
            BatchResults,
            EmbedBatchResults,
            EmbedItem,
            PromptItem,
        )

        value = {
            "BaseLLMClient": BaseLLMClient,
            "BatchResults": BatchResults,
            "EmbedBatchResults": EmbedBatchResults,
            "EmbedItem": EmbedItem,
            "PromptItem": PromptItem,
        }[name]
    elif name in {"LiteLLMBatchClient", "LiteLLMSyncClient"}:
        from context_use.llm.litellm import LiteLLMBatchClient, LiteLLMSyncClient

        value = {
            "LiteLLMBatchClient": LiteLLMBatchClient,
            "LiteLLMSyncClient": LiteLLMSyncClient,
        }[name]
    else:
        from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

        value = {
            "OpenAIEmbeddingModel": OpenAIEmbeddingModel,
            "OpenAIModel": OpenAIModel,
        }[name]

    globals()[name] = value
    return value
