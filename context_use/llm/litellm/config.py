from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from context_use.llm.litellm.models import (
    EmbeddingModel,
    Model,
    OpenAIEmbeddingModel,
    OpenAIModel,
    VertexAIEmbeddingModel,
    VertexAIModel,
)


class BaseLlmConfig(ABC):
    __slots__ = ()

    @property
    @abstractmethod
    def model(self) -> Model: ...

    @property
    @abstractmethod
    def embedding_model(self) -> EmbeddingModel: ...

    @abstractmethod
    def litellm_params(self) -> dict[str, Any]: ...


class OpenAIConfig(BaseLlmConfig):
    __slots__ = ("_model", "_embedding_model", "_api_key")

    def __init__(
        self,
        model: OpenAIModel,
        embedding_model: OpenAIEmbeddingModel,
        api_key: str,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._api_key = api_key

    @property
    def model(self) -> OpenAIModel:
        return self._model

    @property
    def embedding_model(self) -> OpenAIEmbeddingModel:
        return self._embedding_model

    def litellm_params(self) -> dict[str, Any]:
        return {"api_key": self._api_key}


class VertexAIConfig(BaseLlmConfig):
    __slots__ = (
        "_model",
        "_embedding_model",
        "_vertex_project",
        "_vertex_location",
        "_vertex_credentials",
    )

    def __init__(
        self,
        model: VertexAIModel,
        embedding_model: VertexAIEmbeddingModel,
        vertex_project: str,
        vertex_location: str,
        vertex_credentials: str | None = None,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._vertex_project = vertex_project
        self._vertex_location = vertex_location
        self._vertex_credentials = vertex_credentials

    @property
    def model(self) -> VertexAIModel:
        return self._model

    @property
    def embedding_model(self) -> VertexAIEmbeddingModel:
        return self._embedding_model

    def litellm_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "vertex_project": self._vertex_project,
            "vertex_location": self._vertex_location,
        }
        if self._vertex_credentials is not None:
            params["vertex_credentials"] = self._vertex_credentials
        return params
