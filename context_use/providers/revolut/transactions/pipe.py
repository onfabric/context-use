from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import datetime

from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.transaction_types import FALLBACK_INTERACTION_TYPE
from context_use.providers.registry import declare_interaction
from context_use.providers.revolut.transactions.schemas import Model
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

PROVIDER = "revolut"


def _parse_revolut_date(value: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse Revolut date: {value!r}")


class RevolutTransactionsPipe(_BankTransactionPipe):
    provider = PROVIDER
    interaction_type = FALLBACK_INTERACTION_TYPE
    archive_path_pattern = "*/revolut/*.csv"
    display_name = "Revolut"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[BankTransactionRecord]:
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for raw_row in reader:
                row = Model.model_validate(raw_row)
                if row.State == "REVERTED":
                    continue
                authorized_date = (
                    _parse_revolut_date(row.Started_Date) if row.Started_Date else None
                )
                date = (
                    _parse_revolut_date(row.Completed_Date)
                    if row.Completed_Date
                    else _parse_revolut_date(row.Started_Date)
                )
                payment_channel = "in_store" if row.Type == "Card Payment" else None
                yield BankTransactionRecord(
                    date=date,
                    authorized_date=authorized_date,
                    amount=row.Amount,
                    currency=row.Currency,
                    description=row.Description,
                    merchant_name=row.Description,
                    transaction_type=row.Type,
                    payment_channel=payment_channel,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=RevolutTransactionsPipe))
