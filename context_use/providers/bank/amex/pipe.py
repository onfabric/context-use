from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator

from context_use.providers.bank.amex.schemas import Model
from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend


class BankAmexPipe(_BankTransactionPipe):
    interaction_type = "bank_amex"
    archive_path_pattern = "*/amex/*.csv"

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
                amount = f"+{row.amount}" if row.cr == "CR" else f"-{row.amount}"
                foreign_amount = row.foreign_spend_amount or None
                foreign_currency = row.foreign_spend_currency or None
                yield BankTransactionRecord(
                    date=row.process_date,
                    authorized_date=row.transaction_date,
                    amount=amount,
                    currency="GBP",
                    description=row.description,
                    merchant_name=row.description,
                    account_owner=row.cardmember,
                    foreign_amount=foreign_amount,
                    foreign_currency=foreign_currency,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=BankAmexPipe))
