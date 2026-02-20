"""Backward-compat shim — canonical definitions in :mod:`context_use.db.models`."""

from context_use.db.models import Base, TimeStampMixin, _new_uuid, _utcnow

__all__ = ["Base", "TimeStampMixin", "_new_uuid", "_utcnow"]
