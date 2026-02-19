from __future__ import annotations

from pydantic import TypeAdapter

from context_use.etl.payload.models import (
    FibreByType,
    ThreadPayload,
)

FibreTypeAdapter = TypeAdapter(FibreByType)


def make_thread_payload(data: dict) -> ThreadPayload:
    """Create a typed thread payload from a raw dict."""
    return FibreTypeAdapter.validate_python(data)
