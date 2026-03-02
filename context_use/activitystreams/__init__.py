"""
ActivityStreams 2.0 Pydantic Models

This package provides comprehensive Pydantic models for all ActivityStreams 2.0 types
as defined in the W3C ActivityStreams 2.0 Vocabulary specification.

The models are strictly compliant with the W3C specification and include:
- Core Types: Object, Link, Activity, Collection, etc.
- Activity Types: Accept, Add, Announce, Create, etc.
- Actor Types: Person, Organization, Service, etc.
- Object Types: Article, Note, Image, Video, etc.
- Link Types: Link, Mention, and relationship types

Usage:
    from activitystreams import Note, Create, Person

    # Create a note
    note = Note(
        type="Note",
        content="Hello, ActivityStreams!",
        attributedTo="https://example.com/users/alice"
    )

    # Create an activity
    activity = Create(
        type="Create",
        actor="https://example.com/users/alice",
        object=note
    )
"""

# Core types
# Activity types
from .activities import (
    Accept,
    Add,
    Announce,
    Arrive,
    Block,
    Create,
    Delete,
    Dislike,
    Flag,
    Follow,
    Ignore,
    Invite,
    Join,
    Leave,
    Like,
    Listen,
    Move,
    Offer,
    Question,
    Read,
    Reject,
    Remove,
    TentativeAccept,
    TentativeReject,
    Travel,
    Undo,
    Update,
    View,
)

# Actor types
from .actors import (
    Actor,
    Application,
    Group,
    Organization,
    Person,
    Service,
)
from .core import (
    Activity,
    ASType,
    Collection,
    CollectionPage,
    IntransitiveActivity,
    Link,
    Object,
    OrderedCollection,
    OrderedCollectionPage,
)

# Link types and relationship types
from .links import (
    Mention,
)

# Object types
from .objects import (
    Article,
    Audio,
    Document,
    Event,
    Image,
    Note,
    Page,
    Place,
    Profile,
    Relationship,
    Tombstone,
    Video,
)

# All exports organized by category
__all__ = [
    # Core types
    "ASType",
    "Object",
    "Link",
    "Activity",
    "IntransitiveActivity",
    "Collection",
    "OrderedCollection",
    "CollectionPage",
    "OrderedCollectionPage",
    # Activity types
    "Accept",
    "TentativeAccept",
    "Add",
    "Announce",
    "Arrive",
    "Block",
    "Create",
    "Delete",
    "Dislike",
    "Flag",
    "Follow",
    "Ignore",
    "Invite",
    "Join",
    "Leave",
    "Like",
    "Listen",
    "Move",
    "Offer",
    "Question",
    "Reject",
    "TentativeReject",
    "Read",
    "Remove",
    "Travel",
    "Undo",
    "Update",
    "View",
    # Actor types
    "Actor",
    "Application",
    "Group",
    "Organization",
    "Person",
    "Service",
    # Object types
    "Article",
    "Audio",
    "Document",
    "Event",
    "Image",
    "Note",
    "Page",
    "Place",
    "Profile",
    "Relationship",
    "Tombstone",
    "Video",
    # Link types and relationship types
    "Mention",
]
