from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PREFIX = "ctxuse"


@dataclass(frozen=True)
class ProxyHeaders:
    session_id: str
    upstream_host: str
    enrich_enabled: str

    @staticmethod
    def from_prefix(prefix: str) -> ProxyHeaders:
        return ProxyHeaders(
            session_id=f"{prefix}-session-id",
            upstream_host=f"{prefix}-upstream-host",
            enrich_enabled=f"{prefix}-enrich-enabled",
        )
