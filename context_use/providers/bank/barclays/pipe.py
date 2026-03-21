from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterator

from context_use.providers.bank.barclays.schemas import Model
from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

_TYPE_PREFIXES = [
    "Direct Debit",
    "Card Purchase",
    "Standing Order",
    "Bank Transfer",
    "Cash Withdrawal",
    "Cheque",
    "Interest",
]

_TYPE_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _TYPE_PREFIXES) + r")\b"
)


def _extract_transaction_type(description: str) -> str | None:
    m = _TYPE_PATTERN.match(description)
    return m.group(1) if m else None


class BankBarclaysPipe(_BankTransactionPipe):
    interaction_type = "bank_barclays"
    archive_path_pattern = "*/barclays/*.csv"

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
                if row.money_out:
                    amount = f"-{row.money_out}"
                elif row.money_in:
                    amount = f"+{row.money_in}"
                else:
                    continue
                yield BankTransactionRecord(
                    date=row.date,
                    amount=amount,
                    currency="GBP",
                    description=row.description,
                    transaction_type=_extract_transaction_type(row.description),
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=BankBarclaysPipe))
