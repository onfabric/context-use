from enum import StrEnum


class OpenAIModel(StrEnum):
    GPT_4O = "openai/gpt-4o"
    GPT_5_2 = "openai/gpt-5.2"


class OpenAIEmbeddingModel(StrEnum):
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large"
