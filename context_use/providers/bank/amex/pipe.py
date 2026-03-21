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
    institution_name = "Amex"
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
                amount = f"+{row.Amount}" if row.CR == "CR" else f"-{row.Amount}"
                foreign_amount = row.Foreign_Spend_Amount or None
                foreign_currency = row.Foreign_Spend_Currency or None
                yield BankTransactionRecord(
                    date=row.Process_Date,
                    authorized_date=row.Transaction_Date,
                    amount=amount,
                    currency=self.currency,
                    description=row.Description,
                    merchant_name=row.Description,
                    account_owner=row.Cardmember,
                    foreign_amount=foreign_amount,
                    foreign_currency=foreign_currency,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=BankAmexPipe))
