"""User profile context for personalized memory generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProfileContext:
    """Visual context about the user, attached to every memory prompt.

    The face image is used by the LLM to identify the user in photos
    and produce richer, more personal memories.
    """

    face_image_path: str
