from __future__ import annotations

from pydantic import BaseModel


class NetflixMessagesRecord(BaseModel):
    profile_name: str
    message_name: str
    title_name: str
    channel: str
    sent_utc_ts: str
    country_iso_code: str
    device_model: str
    source: str | None = None
