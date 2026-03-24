from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterator

from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.transaction_types import FALLBACK_INTERACTION_TYPE
from context_use.providers.barclays.transactions.schemas import Model
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

PROVIDER = "barclays"

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


class BarclaysTransactionsPipe(_BankTransactionPipe):
    provider = PROVIDER
    interaction_type = FALLBACK_INTERACTION_TYPE
    archive_path_pattern = "*/barclays/*.csv"
    display_name = "Barclays"
    currency = "GBP"

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
                if row.Money_Out:
                    amount = f"-{row.Money_Out}"
                elif row.Money_In:
                    amount = f"+{row.Money_In}"
                else:
                    continue
                yield BankTransactionRecord(
                    date=row.Date,
                    amount=amount,
                    currency=self.currency,
                    description=row.Description,
                    transaction_type=_extract_transaction_type(row.Description),
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=BarclaysTransactionsPipe))
