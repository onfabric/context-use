"""
ActivityStreams 2.0 Link Types.

Link types and relationship types from the AS2 specification.
"""

from typing import Literal

from pydantic import Field

from .core import Link


class Mention(Link):
    """
    A specialized Link that represents an @mention.
    """

    type: Literal["Mention"] = Field("Mention", alias="@type")  # type: ignore[reportIncompatibleVariableOverride]
