"""Shared ID generator for all domain and ORM models."""

from __future__ import annotations

import uuid


def generate_id() -> str:
    """Return a new random UUID string (v4).

    Every model that needs a default ``id`` should use this single
    factory so the generation strategy can be changed in one place.
    """
    return str(uuid.uuid4())
