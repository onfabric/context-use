from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import datetime

from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.revolut.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


def _parse_revolut_date(value: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse Revolut date: {value!r}")


class BankRevolutPipe(_BankTransactionPipe):
    interaction_type = "bank_revolut"
    archive_path_pattern = "*/revolut/*.csv"

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
                if row.state == "REVERTED":
                    continue
                authorized_date = (
                    _parse_revolut_date(row.started_date)
                    if row.started_date
                    else None
                )
                date = (
                    _parse_revolut_date(row.completed_date)
                    if row.completed_date
                    else _parse_revolut_date(row.started_date)
                )
                payment_channel = (
                    "in_store" if row.type == "Card Payment" else None
                )
                yield BankTransactionRecord(
                    date=date,
                    authorized_date=authorized_date,
                    amount=row.amount,
                    currency=row.currency,
                    description=row.description,
                    merchant_name=row.description,
                    transaction_type=row.type,
                    payment_channel=payment_channel,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=BankRevolutPipe))
