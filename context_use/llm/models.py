from enum import StrEnum


class OpenAIModel(StrEnum):
    GPT_4O = "openai/gpt-4o"


class OpenAIEmbeddingModel(StrEnum):
    TEXT_EMBEDDING_3_SMALL = "openai/text-embedding-3-small"
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large"
