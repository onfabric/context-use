"""ActivityStreams 2.0 core + Fibre models (ported from aertex).

This is a self-contained, minimal copy that covers the types used by the
ChatGPT and Instagram providers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ActivityStreams 2.0 Core
# ---------------------------------------------------------------------------


class ASType(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True,
        populate_by_name=True,
        frozen=True,
    )


class Object(ASType):
    type: str = Field("Object", alias="@type")
    id: str | None = Field(None, alias="@id")
    attachment: Object | list[Object] | None = None
    attributedTo: Object | list[Object] | None = None
    content: str | dict[str, str] | None = None
    context: Object | list[Object] | None = None
    name: str | dict[str, str] | None = None
    endTime: datetime | None = None
    published: datetime | None = None
    startTime: datetime | None = None
    summary: str | dict[str, str] | None = None
    updated: datetime | None = None
    url: str | list[str] | None = None
    mediaType: str | None = None
    duration: str | None = None


class Activity(Object):
    type: str = Field("Activity", alias="@type")
    actor: Object | list[Object] | None = None
    object: Object | list[Object] | None = None
    target: Object | list[Object] | None = None
    result: Object | list[Object] | None = None
    origin: Object | list[Object] | None = None
    instrument: Object | list[Object] | None = None


class Collection(Object):
    type: Literal["Collection"] = Field("Collection", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]
    totalItems: int | None = Field(None, ge=0)
    items: list[Object] | None = None


# --- Object subtypes ---


class Note(Object):
    type: Literal["Note"] = Field("Note", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Image(Object):
    type: Literal["Image"] = Field("Image", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Video(Object):
    type: Literal["Video"] = Field("Video", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Profile(Object):
    type: Literal["Profile"] = Field("Profile", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Page(Object):
    type: Literal["Page"] = Field("Page", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


# --- Actor subtypes ---


class Person(Object):
    type: Literal["Person"] = Field("Person", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Application(Object):
    type: Literal["Application"] = Field("Application", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


# --- Activity subtypes ---


class Create(Activity):
    type: Literal["Create"] = Field("Create", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class View(Activity):
    type: Literal["View"] = Field("View", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Follow(Activity):
    type: Literal["Follow"] = Field("Follow", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


# Rebuild forward refs
Object.model_rebuild()
Activity.model_rebuild()
Collection.model_rebuild()
Note.model_rebuild()
Image.model_rebuild()
Video.model_rebuild()
Profile.model_rebuild()
Page.model_rebuild()
Person.model_rebuild()
Application.model_rebuild()
Create.model_rebuild()
View.model_rebuild()
Follow.model_rebuild()


# ---------------------------------------------------------------------------
# Fibre mixin + models
# ---------------------------------------------------------------------------


CURRENT_THREAD_PAYLOAD_VERSION: str = "1.0.0"


class _BaseFibreMixin:
    """Shared utilities for all Fibre types."""

    def unique_key_suffix(self) -> str:
        data = self.to_dict()

        def _sorted(obj):
            if isinstance(obj, dict):
                return {k: _sorted(obj[k]) for k in sorted(obj.keys())}
            if isinstance(obj, list):
                return [_sorted(x) for x in obj]
            return obj

        normalized = _sorted(data)
        payload_str = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        return digest[:16]

    def to_dict(self) -> dict:
        json_str = cast("BaseModel", self).model_dump_json(
            exclude_none=True, by_alias=True
        )
        return json.loads(json_str)

    def get_preview(self, provider: str | None = None) -> str | None:
        try:
            return self._get_preview(provider)
        except Exception as e:
            logger.error("Error getting preview: %s", e)
            return None

    def _get_preview(self, provider: str | None) -> str | None:
        return None

    def get_asat(self) -> datetime | None:
        published = cast("Object", self).published
        if not published:
            return None
        return published


# --- Fibre Objects ---


class FibreTextMessage(Note, _BaseFibreMixin):
    fibreKind: Literal["TextMessage"] = Field("TextMessage", alias="fibre_kind")
    context: Collection | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        content = self.content if isinstance(self.content, str) else ""
        truncated = content[:100] + ("..." if len(content) > 100 else "")
        return f'message "{truncated}"'

    def get_collection(self) -> str | None:
        if self.context and self.context.id:
            return str(self.context.id)
        return None


class FibreImage(Image, _BaseFibreMixin):
    fibreKind: Literal["Image"] = Field("Image", alias="fibre_kind")
    context: Collection | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        return "image"

    def get_collection(self) -> str | None:
        if self.context and self.context.id:
            return str(self.context.id)
        return None


class FibreVideo(Video, _BaseFibreMixin):
    fibreKind: Literal["Video"] = Field("Video", alias="fibre_kind")
    context: Collection | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        return "video"

    def get_collection(self) -> str | None:
        if self.context and self.context.id:
            return str(self.context.id)
        return None


class FibreCollection(Collection, _BaseFibreMixin):
    fibreKind: Literal["Collection"] = Field("Collection", alias="fibre_kind")

    def _get_preview(self, provider: str | None) -> str | None:
        parts = ["collection"]
        if self.name:
            parts.append(f'"{self.name}"')
        return " ".join(parts)


# --- Fibre Activities ---


class FibreCreateObject(Create, _BaseFibreMixin):
    fibreKind: Literal["Create"] = Field("Create", alias="fibre_kind")
    object: Image | Video  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    target: FibreCollection | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Posted {self.object.type.lower()}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreSendMessage(Create, _BaseFibreMixin):
    fibreKind: Literal["SendMessage"] = Field("SendMessage", alias="fibre_kind")
    object: FibreTextMessage | FibreImage | FibreVideo  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    actor: None = None  # type: ignore[reportIncompatibleVariableOverride]
    target: Profile | Application  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Sent {self.object._get_preview(provider)} to {self.target.name}"
        if provider:
            parts += f" on {provider}"
        return parts

    def get_collection(self) -> str | None:
        return self.object.get_collection()


class FibreReceiveMessage(Create, _BaseFibreMixin):
    fibreKind: Literal["ReceiveMessage"] = Field("ReceiveMessage", alias="fibre_kind")
    object: FibreTextMessage | FibreImage | FibreVideo  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    actor: Profile | Application  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    target: None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Received {self.object._get_preview(provider)} from {self.actor.name}"
        if provider:
            parts += f" on {provider}"
        return parts

    def get_collection(self) -> str | None:
        return self.object.get_collection()


# --- Discriminated union ---

FibreByType = Annotated[
    FibreCreateObject
    | FibreImage
    | FibreVideo
    | FibreCollection
    | FibreSendMessage
    | FibreReceiveMessage,
    Field(discriminator="fibreKind"),
]

ThreadPayload = FibreByType


# Rebuild all fibre models
FibreTextMessage.model_rebuild()
FibreImage.model_rebuild()
FibreVideo.model_rebuild()
FibreCollection.model_rebuild()
FibreCreateObject.model_rebuild()
FibreSendMessage.model_rebuild()
FibreReceiveMessage.model_rebuild()
