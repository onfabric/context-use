"""
ActivityStreams 2.0 Activity Types.

All activity types from the AS2 specification.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .core import Activity, IntransitiveActivity, Link, Object


class Accept(Activity):
    """
    Indicates that the actor accepts the object. The target property can be
    used in certain circumstances to indicate the context into which the
    object has been accepted.
    """

    type: Literal["Accept"] = Field("Accept", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class TentativeAccept(Accept):
    """
    A specialization of Accept indicating that the acceptance is tentative.
    """

    type: Literal["TentativeAccept"] = Field("TentativeAccept", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Add(Activity):
    """
    Indicates that the actor has added the object to the target. If the target
    property is not explicitly specified, the target would need to be
    determined implicitly by context.
    """

    type: Literal["Add"] = Field("Add", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Announce(Activity):
    """
    Indicates that the actor is calling the target's attention the object.
    """

    type: Literal["Announce"] = Field("Announce", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Arrive(IntransitiveActivity):
    """
    An IntransitiveActivity that indicates that the actor has arrived at
    the location. The origin can be used to identify the context from which
    the actor originated.
    """

    type: Literal["Arrive"] = Field("Arrive", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Block(Activity):
    """
    Indicates that the actor is blocking the object.
    """

    type: Literal["Block"] = Field("Block", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Create(Activity):
    """
    Indicates that the actor has created the object.
    """

    type: Literal["Create"] = Field("Create", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Delete(Activity):
    """
    Indicates that the actor has deleted the object. If specified, the origin
    indicates the context from which the object was deleted.
    """

    type: Literal["Delete"] = Field("Delete", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Dislike(Activity):
    """
    Indicates that the actor dislikes the object.
    """

    type: Literal["Dislike"] = Field("Dislike", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Flag(Activity):
    """
    Indicates that the actor is "flagging" the object.
    """

    type: Literal["Flag"] = Field("Flag", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Follow(Activity):
    """
    Indicates that the actor is "following" the object.
    """

    type: Literal["Follow"] = Field("Follow", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Ignore(Activity):
    """
    Indicates that the actor is ignoring the object.
    """

    type: Literal["Ignore"] = Field("Ignore", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Invite(Activity):
    """
    A specialization of Offer in which the actor is extending an invitation
    for the object to the target.
    """

    type: Literal["Invite"] = Field("Invite", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Join(Activity):
    """
    Indicates that the actor has joined the object.
    """

    type: Literal["Join"] = Field("Join", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Leave(Activity):
    """
    Indicates that the actor has left the object.
    """

    type: Literal["Leave"] = Field("Leave", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Like(Activity):
    """
    Indicates that the actor likes, recommends or endorses the object.
    """

    type: Literal["Like"] = Field("Like", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Listen(Activity):
    """
    Indicates that the actor has listened to the object.
    """

    type: Literal["Listen"] = Field("Listen", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Move(Activity):
    """
    Indicates that the actor has moved object from origin to target.
    """

    type: Literal["Move"] = Field("Move", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Offer(Activity):
    """
    Indicates that the actor is offering the object.
    """

    type: Literal["Offer"] = Field("Offer", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Question(IntransitiveActivity):
    """
    Represents a question being asked.
    """

    type: Literal["Question"] = Field("Question", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]

    # Question-specific properties
    oneOf: list[Object | Link] | None = None
    anyOf: list[Object | Link] | None = None
    closed: datetime | bool | None = None


class Reject(Activity):
    """
    Indicates that the actor is rejecting the object.
    """

    type: Literal["Reject"] = Field("Reject", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class TentativeReject(Reject):
    """
    A specialization of Reject in which the rejection is considered tentative.
    """

    type: Literal["TentativeReject"] = Field("TentativeReject", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Read(Activity):
    """
    Indicates that the actor has read the object.
    """

    type: Literal["Read"] = Field("Read", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Remove(Activity):
    """
    Indicates that the actor is removing the object.
    """

    type: Literal["Remove"] = Field("Remove", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Travel(IntransitiveActivity):
    """
    Indicates that the actor is traveling to target from origin.
    """

    type: Literal["Travel"] = Field("Travel", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Undo(Activity):
    """
    Indicates that the actor is undoing the object.
    """

    type: Literal["Undo"] = Field("Undo", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Update(Activity):
    """
    Indicates that the actor has updated the object.
    """

    type: Literal["Update"] = Field("Update", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class View(Activity):
    """
    Indicates that the actor has viewed the object.
    """

    type: Literal["View"] = Field("View", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


# Update forward references for proper type resolution
Accept.model_rebuild()
TentativeAccept.model_rebuild()
Add.model_rebuild()
Announce.model_rebuild()
Arrive.model_rebuild()
Block.model_rebuild()
Create.model_rebuild()
Delete.model_rebuild()
Dislike.model_rebuild()
Flag.model_rebuild()
Follow.model_rebuild()
Ignore.model_rebuild()
Invite.model_rebuild()
Join.model_rebuild()
Leave.model_rebuild()
Like.model_rebuild()
Listen.model_rebuild()
Move.model_rebuild()
Offer.model_rebuild()
Question.model_rebuild()
Reject.model_rebuild()
TentativeReject.model_rebuild()
Read.model_rebuild()
Remove.model_rebuild()
Travel.model_rebuild()
Undo.model_rebuild()
Update.model_rebuild()
View.model_rebuild()
