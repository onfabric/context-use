from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PREFIX = "ctxuse"


@dataclass(frozen=True)
class ProxyHeaders:
    session_id: str

    @staticmethod
    def from_prefix(prefix: str) -> ProxyHeaders:
        return ProxyHeaders(session_id=f"{prefix}-session-id")
