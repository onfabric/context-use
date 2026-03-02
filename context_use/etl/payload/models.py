from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field

from context_use.activitystreams.activities import Create, View
from context_use.activitystreams.actors import Application
from context_use.activitystreams.core import Collection, Object
from context_use.activitystreams.objects import Image, Note, Page, Profile, Video

logger = logging.getLogger(__name__)


CURRENT_THREAD_PAYLOAD_VERSION: str = "1.0.0"


class _BaseFibreMixin:
    """Shared utilities for all Fibre types."""

    def unique_key(self) -> str:
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
        # NOTE: Serialises using Python field names (type, fibreKind) to match
        # aertex's current wire format.  A future migration will switch both
        # repos to by_alias=True for proper AS2.0 keys (@type, fibre_kind)
        # and eventually retire the non-standard fibreKind extension entirely.
        json_str = cast("BaseModel", self).model_dump_json(exclude_none=True)
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

    def get_collection(self) -> str | None:
        """Get collection ID for this fibre."""
        return None

    def is_inbound(self) -> bool:
        """Whether this interaction was performed by someone else toward the user."""
        return False

    def get_message_content(self) -> str | None:
        """Get the core textual content of a message interaction.

        Default to None as most interaction types are not messages.
        """
        return None


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

    def get_message_content(self) -> str | None:
        return self.object.content if isinstance(self.object.content, str) else None

    def get_collection(self) -> str | None:
        return self.object.get_collection()


class FibreReceiveMessage(Create, _BaseFibreMixin):
    fibreKind: Literal["ReceiveMessage"] = Field("ReceiveMessage", alias="fibre_kind")
    object: FibreTextMessage | FibreImage | FibreVideo  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    actor: Profile | Application  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    target: None = None  # type: ignore[reportIncompatibleVariableOverride]

    def is_inbound(self) -> bool:
        return True

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Received {self.object._get_preview(provider)} from {self.actor.name}"
        if provider:
            parts += f" on {provider}"
        return parts

    def get_message_content(self) -> str | None:
        return self.object.content if isinstance(self.object.content, str) else None

    def get_collection(self) -> str | None:
        return self.object.get_collection()


class FibreViewObject(View, _BaseFibreMixin):
    fibreKind: Literal["View"] = Field("View", alias="fibre_kind")
    object: Page | Video  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = [
            f"Viewed {self.object.type.lower()}",
        ]
        if self.object.name:
            parts.append(f'"{self.object.name}"')
        else:
            if self.object.url:
                parts.append(f"{self.object.url}")
        if self.object.attributedTo:
            attr = self.object.attributedTo
            if isinstance(attr, list):
                attr = attr[0]
            parts.append(f"by {attr.name}")
        if provider:
            if provider.lower() == "google":
                parts.append(f"via {provider}")
            else:
                parts.append(f"on {provider}")
        return " ".join(parts)


# --- Discriminated union ---

FibreByType = Annotated[
    FibreCreateObject
    | FibreImage
    | FibreVideo
    | FibreCollection
    | FibreSendMessage
    | FibreReceiveMessage
    | FibreViewObject,
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
FibreViewObject.model_rebuild()
