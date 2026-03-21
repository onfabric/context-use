from enum import StrEnum
from typing import Self


class _BaseModel(StrEnum):
    def __init__(self, value: str) -> None:
        parts = self.value.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid model value: {self.value}")
        self._provider_name = parts[0]
        self._model_name = parts[1]
        super().__init__()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name


class OpenAIModel(_BaseModel):
    GPT_5_2 = "openai/gpt-5.2"


class VertexAIModel(_BaseModel):
    GEMINI_2_5_FLASH = "vertex_ai/gemini-2.5-flash"


type Model = OpenAIModel | VertexAIModel


class _BaseEmbeddingModel(_BaseModel):
    embedding_dimensions: int

    def __new__(cls, value: str, embedding_dimensions: int) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj

    def __init__(self, value: str, embedding_dimensions: int) -> None:
        self.embedding_dimensions = embedding_dimensions
        super().__init__(value)


class OpenAIEmbeddingModel(_BaseEmbeddingModel):
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large", 3072


class VertexAIEmbeddingModel(_BaseEmbeddingModel):
    TEXT_EMBEDDING_005 = "vertex_ai/text-embedding-005", 768


type EmbeddingModel = OpenAIEmbeddingModel | VertexAIEmbeddingModel
