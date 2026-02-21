from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ThreadRow:
    """Plain value object flowing from Pipe.transform() to Loader.load().

    Contains only the domain data needed to represent a thread.
    Infrastructure concerns (``id``, ``etl_task_id``, timestamps) are
    added by the Loader when persisting.
    """

    unique_key: str
    provider: str
    interaction_type: str
    preview: str
    payload: dict
    version: str
    asat: datetime
    source: str | None = None
    asset_uri: str | None = None
