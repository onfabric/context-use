"""
ActivityStreams 2.0 Core Types

This module contains the core types defined in the ActivityStreams 2.0 specification:
- Object: Base type for all objects
- Link: Indirect reference to resources
- Activity: Describes actions
- IntransitiveActivity: Actions without objects
- Collection: Sets of objects/links
- OrderedCollection: Ordered sets
- CollectionPage: Paginated subsets
- OrderedCollectionPage: Ordered paginated subsets
"""

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ASType(BaseModel):
    """Base class for all ActivityStreams objects and links."""

    model_config = ConfigDict(
        extra="allow",  # accept extension properties
        use_enum_values=True,  # enums -> their values
        populate_by_name=True,  # use field names for serialization
        frozen=True,  # make instances immutable
    )


class Object(ASType):
    """
    Base Object type as defined in ActivityStreams 2.0.

    Describes an object of any kind. The Object type serves as the base type
    for most of the other kinds of objects defined in the Activity Vocabulary.
    """

    # Core properties
    type: str = Field("Object", alias="@type")
    id: HttpUrl | None = Field(None, alias="@id")

    # Object properties
    attachment: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    attributedTo: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    audience: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    content: str | dict[str, str] | None = None  # Natural language value
    context: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    name: str | dict[str, str] | None = None  # Natural language value
    endTime: datetime | None = None
    generator: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    icon: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    image: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    inReplyTo: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    location: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    preview: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    published: datetime | None = None
    replies: Optional["Collection"] = None
    startTime: datetime | None = None
    summary: str | dict[str, str] | None = None  # Natural language value
    tag: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    updated: datetime | None = None
    url: Union[HttpUrl, "Link", list[Union[HttpUrl, "Link"]]] | None = None

    # Audience targeting
    to: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    bto: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    cc: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    bcc: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None

    # Additional properties
    mediaType: str | None = None
    duration: str | None = None  # ISO 8601 duration


class Link(ASType):
    """
    A Link is an indirect, qualified reference to a resource identified by a URL.

    The fundamental model for links is established by RFC5988. Many of the
    properties defined by the Activity Vocabulary allow values that are either
    instances of Object or Link.
    """

    # Required
    type: Literal["Link"] = Field("Link", alias="@type")
    href: HttpUrl

    # Optional properties
    rel: str | list[str] | None = None
    mediaType: str | None = None
    name: str | dict[str, str] | None = None
    hreflang: str | None = None
    height: int | None = Field(None, ge=0)
    width: int | None = Field(None, ge=0)
    preview: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None


class Activity(Object):
    """
    An Activity is a subtype of Object that describes some form of action
    that may happen, is currently happening, or has already happened.
    """

    type: str = Field("Activity", alias="@type")
    # Activity-specific properties
    actor: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    object: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    target: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    result: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    origin: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None
    instrument: Union["Object", "Link", list[Union["Object", "Link"]]] | None = None


class IntransitiveActivity(Activity):
    """
    Instances of IntransitiveActivity are a subtype of Activity representing
    intransitive actions. The object property is therefore inappropriate for
    these activities.
    """

    # Override to exclude object property
    object: None = Field(None, exclude=True)  # type: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]


class Collection(Object):
    """
    A Collection is a subtype of Object that represents ordered or unordered
    sets of Object or Link instances.
    """

    type: Literal["Collection"] = Field("Collection", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]
    totalItems: int | None = Field(None, ge=0)
    current: Union["CollectionPage", "Link"] | None = None
    first: Union["CollectionPage", "Link"] | None = None
    last: Union["CollectionPage", "Link"] | None = None
    items: list[Union["Object", "Link"]] | None = None


class OrderedCollection(Collection):
    """
    A subtype of Collection in which members of the logical collection are
    assumed to always be strictly ordered.
    """

    orderedItems: list[Union["Object", "Link"]] | None = None


class CollectionPage(Collection):
    """
    Used to represent distinct subsets of items from a Collection.
    """

    partOf: Union["Collection", "Link"] | None = None
    next: Union["CollectionPage", "Link"] | None = None
    prev: Union["CollectionPage", "Link"] | None = None


class OrderedCollectionPage(CollectionPage, OrderedCollection):
    """
    Used to represent ordered subsets of items from an OrderedCollection.
    """

    startIndex: int | None = Field(None, ge=0)


# Update forward references for proper type resolution
Object.model_rebuild()
Link.model_rebuild()
Activity.model_rebuild()
IntransitiveActivity.model_rebuild()
Collection.model_rebuild()
OrderedCollection.model_rebuild()
CollectionPage.model_rebuild()
OrderedCollectionPage.model_rebuild()
