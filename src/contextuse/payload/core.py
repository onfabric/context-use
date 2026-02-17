"""Thread payload utilities (ported from aertex)."""

from __future__ import annotations

from pydantic import TypeAdapter

from contextuse.payload.models import (
    FibreByType,
    ThreadPayload,
    CURRENT_THREAD_PAYLOAD_VERSION,
)

FibreTypeAdapter = TypeAdapter(FibreByType)


def make_thread_payload(data: dict) -> ThreadPayload:
    """Create a typed thread payload from a raw dict."""
    return FibreTypeAdapter.validate_python(data)

