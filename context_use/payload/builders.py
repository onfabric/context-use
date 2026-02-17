"""Payload builders (ported from aertex)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from context_use.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Collection,
    Person,
    Profile,
    ThreadPayload,
)


class BaseThreadPayloadBuilder(ABC):
    """Base class for provider-specific payload construction."""

    def __init__(self, input_fields=None):
        self.input_fields = input_fields

    def get_version(self) -> str:
        return CURRENT_THREAD_PAYLOAD_VERSION

    @abstractmethod
    def build(self, parsed_item) -> ThreadPayload:
        """Create the specific fibre type for this provider."""
        ...


class ProfileBuilder:
    def __init__(self, url: str | None = None):
        self.url = url
        self.name: str | None = None
        self.is_actor = False

    def set_actor(self):
        self.is_actor = True
        return self

    def with_name(self, name: str):
        self.name = name
        return self

    def build(self) -> Profile | Person:
        if self.is_actor:
            return Person(name=self.name, url=self.url)
        return Profile(name=self.name, url=self.url)


class CollectionBuilder:
    def __init__(self):
        self.name: str | None = None
        self.id: str | None = None

    def with_name(self, name: str):
        self.name = name
        return self

    def with_id(self, id_: str):
        self.id = id_
        return self

    def build(self) -> Collection:
        kwargs: dict = {"type": "Collection"}
        if self.name is not None:
            kwargs["name"] = self.name
        if self.id is not None:
            kwargs["id"] = self.id
        return Collection(**kwargs)


class PublishedBuilder:
    def __init__(self, published: datetime):
        if not isinstance(published, datetime):
            raise ValueError("PublishedBuilder requires a datetime")
        self._published = published

    def build(self) -> datetime:
        return self._published
