from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field, model_validator

from context_use.activitystreams.activities import (
    Add,
    Create,
    Dislike,
    Follow,
    Like,
    View,
)
from context_use.activitystreams.actors import Application, Person
from context_use.activitystreams.core import Collection, Object
from context_use.activitystreams.objects import Event, Image, Note, Page, Profile, Video

logger = logging.getLogger(__name__)


CURRENT_THREAD_PAYLOAD_VERSION: str = "1.1.0"


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

    def get_participant_label(self) -> str:
        return "ME"


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


class FibrePost(Note, _BaseFibreMixin):
    """A post object — nested-only, not in FibreByType."""

    fibreKind: Literal["Post"] = Field("Post", alias="fibre_kind")
    attributedTo: Profile | None = None  # type: ignore[reportIncompatibleVariableOverride]


class FibreAd(Object, _BaseFibreMixin):
    fibreKind: Literal["Ad"] = Field("Ad", alias="fibre_kind")
    attributedTo: Profile | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = ["ad"]
        if self.name:
            parts.append(str(self.name))
        if self.attributedTo and self.attributedTo.name:
            parts.append(f"by {self.attributedTo.name}")
        return " ".join(parts)


class FibreCollectionFavourites(FibreCollection):
    """Favourites collection — nested-only, not in FibreByType."""

    fibreKind: Literal["CollectionFavourites"] = Field(  # type: ignore[reportIncompatibleVariableOverride]
        "CollectionFavourites", alias="fibre_kind"
    )
    name: Literal["Favourites"] = "Favourites"  # type: ignore[reportIncompatibleVariableOverride]


# --- Fibre Mixins ---


class _BaseFibreFollowXORMixin:
    """Validates that exactly one of actor or object is set on Follow fibres."""

    @model_validator(mode="after")
    def _xor(self):
        has_actor = self.actor is not None  # type: ignore[attr-defined]
        has_object = self.object is not None  # type: ignore[attr-defined]
        if has_actor == has_object:
            raise ValueError("Exactly one of actor or object must be set")
        return self


class FibreReaction(BaseModel):
    """Marker mixin for reaction-type activities (Like, Dislike)."""

    fibreKind: Literal["Reaction"] = Field("Reaction", alias="fibre_kind")
    object: FibrePost | Video
    content: str | None = None

    @model_validator(mode="after")
    def _validate_content(self):
        if self.content is not None and not self.content:
            raise ValueError("Reaction content must be non-empty when provided")
        return self


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
    actor: Profile | Application | Person  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    target: None = None  # type: ignore[reportIncompatibleVariableOverride]

    def is_inbound(self) -> bool:
        return True

    def get_participant_label(self) -> str:
        name = self.actor.name
        if isinstance(name, str):
            return name
        return "THEM"

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
    object: Page | Video | FibrePost | Event  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        if isinstance(self.object, FibrePost):
            type_label = "post"
        else:
            type_label = self.object.type.lower()
        parts = [f"Viewed {type_label}"]
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


class FibreViewAdObject(FibreViewObject):
    fibreKind: Literal["ViewAd"] = Field("ViewAd", alias="fibre_kind")  # type: ignore[reportIncompatibleVariableOverride]
    object: FibreAd  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Viewed {self.object.get_preview(provider)}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreClickAdObject(FibreViewAdObject):
    fibreKind: Literal["ClickAd"] = Field("ClickAd", alias="fibre_kind")  # type: ignore[reportIncompatibleVariableOverride]
    object: FibreAd  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        parts = f"Clicked {self.object.get_preview(provider)}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreLike(FibreReaction, Like, _BaseFibreMixin):  # type: ignore[reportIncompatibleVariableOverride]
    """Inherits fibreKind="Reaction" from FibreReaction, type="Like" from Like."""

    def _get_preview(self, provider: str | None) -> str | None:
        if isinstance(self.object, FibrePost):
            parts = "Liked post"
            if self.object.attributedTo:
                parts += f" by {self.object.attributedTo.name}"
        elif self.object.name:
            parts = f'Liked "{self.object.name}"'
        else:
            parts = f"Liked {self.object.type.lower()}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreDislike(FibreReaction, Dislike, _BaseFibreMixin):  # type: ignore[reportIncompatibleVariableOverride]
    """Inherits fibreKind="Reaction" from FibreReaction, type="Dislike" from Dislike."""

    def _get_preview(self, provider: str | None) -> str | None:
        if isinstance(self.object, FibrePost):
            parts = "Disliked post"
            if self.object.attributedTo:
                parts += f" by {self.object.attributedTo.name}"
        elif self.object.name:
            parts = f'Disliked "{self.object.name}"'
        else:
            parts = f"Disliked {self.object.type.lower()}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreComment(Create, _BaseFibreMixin):
    fibreKind: Literal["Comment"] = Field("Comment", alias="fibre_kind")
    object: Note  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    inReplyTo: FibrePost | Page | None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        content = self.object.content if isinstance(self.object.content, str) else ""
        truncated = content[:80] + ("..." if len(content) > 80 else "")
        parts = f'Commented "{truncated}"'
        if isinstance(self.inReplyTo, FibrePost) and self.inReplyTo.attributedTo:
            parts += f" on {self.inReplyTo.attributedTo.name}'s post"
        elif isinstance(self.inReplyTo, Page):
            parts += " on listing" if provider == "Airbnb" else " on page"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreSearch(View, _BaseFibreMixin):
    fibreKind: Literal["Search"] = Field("Search", alias="fibre_kind")
    object: FibrePost | Page | Profile  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        if isinstance(self.object, Profile):
            parts = f'Searched for profile "{self.object.name}"'
        elif isinstance(self.object, FibrePost):
            parts = "Searched for post"
        else:
            name = self.object.name or ""
            parts = f'Searched "{name}"'
        if provider:
            parts += f" on {provider}"
        return parts


class FibreAddObjectToCollection(Add, _BaseFibreMixin):
    fibreKind: Literal["AddToCollection"] = Field("AddToCollection", alias="fibre_kind")
    object: Video | Image | Page | FibrePost  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    target: FibreCollectionFavourites | FibreCollection | Collection  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]

    def _get_preview(self, provider: str | None) -> str | None:
        if isinstance(self.target, FibreCollectionFavourites):
            parts = "Saved"
        elif self.target and self.target.name:
            parts = f'Saved to "{self.target.name}"'
        else:
            parts = "Saved"
        if isinstance(self.object, FibrePost):
            if self.object.attributedTo:
                parts += f" post by {self.object.attributedTo.name}"
            else:
                parts += " post"
        elif isinstance(self.object, Page):
            parts += " page"
        elif isinstance(self.object, (Image, Video)):
            parts += f" {self.object.type.lower()}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreFollowedBy(Follow, _BaseFibreMixin, _BaseFibreFollowXORMixin):
    fibreKind: Literal["FollowedBy"] = Field("FollowedBy", alias="fibre_kind")
    actor: Person  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    object: None = None  # type: ignore[reportIncompatibleVariableOverride]

    def is_inbound(self) -> bool:
        return True

    def _get_preview(self, provider: str | None) -> str | None:
        name = self.actor.name if self.actor else "someone"
        parts = f"Followed by {name}"
        if provider:
            parts += f" on {provider}"
        return parts


class FibreFollowing(Follow, _BaseFibreMixin, _BaseFibreFollowXORMixin):
    fibreKind: Literal["Following"] = Field("Following", alias="fibre_kind")
    object: Profile | Page  # type: ignore[reportIncompatibleVariableOverride, reportGeneralTypeIssues]
    actor: None = None  # type: ignore[reportIncompatibleVariableOverride]

    def _get_preview(self, provider: str | None) -> str | None:
        name = self.object.name if self.object else "someone"
        parts = f"Following {name}"
        if provider:
            parts += f" on {provider}"
        return parts


# --- Discriminated unions ---

FibreReactionByType = Annotated[
    FibreLike | FibreDislike,
    Field(discriminator="type"),
]

FibreByType = Annotated[
    FibreClickAdObject
    | FibreViewAdObject
    | FibreViewObject
    | FibreCreateObject
    | FibreAddObjectToCollection
    | FibreSearch
    | FibreReactionByType
    | FibreImage
    | FibreVideo
    | FibreCollection
    | FibreSendMessage
    | FibreReceiveMessage
    | FibreComment,
    Field(discriminator="fibreKind"),
]

FibreFollow = FibreFollowedBy | FibreFollowing
Fibre = FibreByType | FibreFollow
ThreadPayload = Fibre


# Rebuild all fibre models
FibreTextMessage.model_rebuild()
FibreImage.model_rebuild()
FibreVideo.model_rebuild()
FibreCollection.model_rebuild()
FibrePost.model_rebuild()
FibreCollectionFavourites.model_rebuild()
FibreReaction.model_rebuild()
FibreAd.model_rebuild()
FibreCreateObject.model_rebuild()
FibreSendMessage.model_rebuild()
FibreReceiveMessage.model_rebuild()
FibreViewObject.model_rebuild()
FibreViewAdObject.model_rebuild()
FibreClickAdObject.model_rebuild()
FibreLike.model_rebuild()
FibreDislike.model_rebuild()
FibreComment.model_rebuild()
FibreSearch.model_rebuild()
FibreAddObjectToCollection.model_rebuild()
FibreFollowedBy.model_rebuild()
FibreFollowing.model_rebuild()
