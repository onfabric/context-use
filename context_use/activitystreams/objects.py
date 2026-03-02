"""
ActivityStreams 2.0 Object Types.

All object types from the AS2 specification.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl

from .core import Link, Object


class Article(Object):
    """
    Represents any kind of multi-paragraph written work.
    """

    type: Literal["Article"] = Field("Article", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Audio(Object):
    """
    Represents an audio document of any kind.
    """

    type: Literal["Audio"] = Field("Audio", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Document(Object):
    """
    Represents a document of any kind.
    """

    type: Literal["Document"] = Field("Document", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Event(Object):
    """
    Represents any kind of event.
    """

    type: Literal["Event"] = Field("Event", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Image(Object):
    """
    An image document of any kind.
    """

    type: Literal["Image"] = Field("Image", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Note(Object):
    """
    Represents a short written work typically less than a single paragraph in length.
    """

    type: Literal["Note"] = Field("Note", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Page(Object):
    """
    Represents a Web Page.
    """

    type: Literal["Page"] = Field("Page", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Place(Object):
    """
    Represents a logical or physical location.
    """

    type: Literal["Place"] = Field("Place", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]

    # Place-specific properties
    accuracy: float | None = Field(None, ge=0.0, le=100.0)
    altitude: float | None = None
    latitude: float | None = Field(None, ge=-90.0, le=90.0)
    longitude: float | None = Field(None, ge=-180.0, le=180.0)
    radius: float | None = Field(None, ge=0.0)
    units: str | None = None


class Profile(Object):
    """
    A Profile is a content object that describes another Object.
    """

    type: Literal["Profile"] = Field("Profile", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]

    # Profile-specific properties
    describes: Object | Link | None = None


class Relationship(Object):
    """
    Describes a relationship between two individuals.
    """

    type: Literal["Relationship"] = Field("Relationship", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]

    # Relationship-specific properties
    subject: Object | Link | None = None
    # per AS2, relationship property has a domain Object
    # but per JSON-LD notation, an IRI string is an object
    # i.e. the following 2 examples are identical
    # "relationship": "http://purl.org/vocab/relationship/acquaintanceOf"
    # "relationship": { "id": "http://purl.org/vocab/relationship/acquaintanceOf" }
    relationship: Object | HttpUrl | None = None


class Tombstone(Object):
    """
    A Tombstone represents a content object that has been deleted.
    """

    type: Literal["Tombstone"] = Field("Tombstone", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]

    # Tombstone-specific properties
    formerType: str | list[str] | None = None
    deleted: datetime | None = None


class Video(Object):
    """
    Represents a video document of any kind.
    """

    type: Literal["Video"] = Field("Video", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


# Update forward references for proper type resolution
Article.model_rebuild()
Audio.model_rebuild()
Document.model_rebuild()
Event.model_rebuild()
Image.model_rebuild()
Note.model_rebuild()
Page.model_rebuild()
Place.model_rebuild()
Profile.model_rebuild()
Relationship.model_rebuild()
Tombstone.model_rebuild()
Video.model_rebuild()
