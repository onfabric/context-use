from __future__ import annotations

from datetime import UTC, datetime

from context_use.activitystreams.actors import Person
from context_use.activitystreams.objects import Note
from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    FibreTransaction,
)
from context_use.models.etl_task import EtlTask
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.schemas import PROVIDER


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


class _BankTransactionPipe(Pipe[BankTransactionRecord]):
    provider = PROVIDER
    archive_version = 1
    record_schema = BankTransactionRecord
    institution_name: str

    def transform(
        self,
        record: BankTransactionRecord,
        task: EtlTask,
    ) -> ThreadRow:
        published = _parse_date(record.date)
        note = Note(  # type: ignore[reportCallIssue]
            name=record.amount,
            content=record.merchant_name or record.description,
            published=published,
        )
        actor = Person(name=record.account_owner) if record.account_owner else None  # type: ignore[reportCallIssue]
        payload = FibreTransaction(  # type: ignore[reportCallIssue]
            object=note,
            published=published,
            actor=actor,
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(self.institution_name) or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=published,
            source=record.source,
        )
