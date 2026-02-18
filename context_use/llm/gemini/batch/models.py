"""Data models for the Gemini Batch API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BatchJobState(StrEnum):
    """Google Gemini batch job states."""

    SUCCEEDED = "JOB_STATE_SUCCEEDED"
    FAILED = "JOB_STATE_FAILED"
    CANCELLED = "JOB_STATE_CANCELLED"
    EXPIRED = "JOB_STATE_EXPIRED"
    PENDING = "JOB_STATE_PENDING"
    RUNNING = "JOB_STATE_RUNNING"

    @classmethod
    def is_completed(cls, state: str) -> bool:
        return state in {
            cls.SUCCEEDED.value,
            cls.FAILED.value,
            cls.CANCELLED.value,
            cls.EXPIRED.value,
        }

    @classmethod
    def is_successful(cls, state: str) -> bool:
        return state == cls.SUCCEEDED.value


@dataclass
class BatchJobResult:
    """Status snapshot returned by :func:`get_batch_job_status`."""

    job_name: str
    state: str
    dest_file: str | None = None
    error: str | None = None
