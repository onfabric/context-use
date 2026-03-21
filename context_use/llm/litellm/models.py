from enum import StrEnum


class OpenAIModel(StrEnum):
    GPT_4O = "openai/gpt-4o"
    GPT_5_2 = "openai/gpt-5.2"


class VertexAIModel(StrEnum):
    GEMINI_2_5_FLASH = "vertex_ai/gemini-2.5-flash"


type Model = OpenAIModel | VertexAIModel


class OpenAIEmbeddingModel(StrEnum):
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large"
    TEXT_EMBEDDING_3_SMALL = "openai/text-embedding-3-small"


class VertexAIEmbeddingModel(StrEnum):
    TEXT_EMBEDDING_004 = "vertex_ai/text-embedding-004"


type EmbeddingModel = OpenAIEmbeddingModel | VertexAIEmbeddingModel
