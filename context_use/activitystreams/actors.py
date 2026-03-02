"""
ActivityStreams 2.0 Actor Types.

All actor types from the AS2 specification.
"""

from typing import Literal

from pydantic import Field

from .core import Object


class Actor(Object):
    """Base class for all Actor types."""


class Application(Actor):
    """
    Describes a software application.
    """

    type: Literal["Application"] = Field("Application", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Group(Actor):
    """
    Represents an informal group of people.
    """

    type: Literal["Group"] = Field("Group", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Organization(Actor):
    """
    Represents an organization.
    """

    type: Literal["Organization"] = Field("Organization", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Person(Actor):
    """
    Represents an individual person.
    """

    type: Literal["Person"] = Field("Person", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]


class Service(Actor):
    """
    Represents a service of any kind.
    """

    type: Literal["Service"] = Field("Service", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]
