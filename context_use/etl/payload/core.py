from pydantic import TypeAdapter

from context_use.etl.payload.models import (
    FibreByType,
    FibreFollowedBy,
    FibreFollowing,
    ThreadPayload,
)

FibreTypeAdapter = TypeAdapter(FibreByType)


def make_thread_payload(data: dict) -> ThreadPayload:
    """Create a typed thread payload from a raw dict."""
    raw_type = data.get("type")
    if raw_type == "Follow":
        has_actor = data.get("actor") is not None
        has_object = data.get("object") is not None
        if has_actor ^ has_object:
            if has_actor:
                return FibreFollowedBy.model_validate(data)
            else:
                return FibreFollowing.model_validate(data)
    return FibreTypeAdapter.validate_python(data)
