from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator

from context_use.providers.amex.transactions.schemas import Model
from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.transaction_types import FALLBACK_INTERACTION_TYPE
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

PROVIDER = "amex"


class AmexTransactionsPipe(_BankTransactionPipe):
    provider = PROVIDER
    interaction_type = FALLBACK_INTERACTION_TYPE
    archive_path_pattern = "*/amex/*.csv"
    display_name = "Amex"
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
                if row.CR == "CR":
                    amount = f"+{row.Amount}"
                    transaction_type = "Payment"
                else:
                    amount = f"-{row.Amount}"
                    transaction_type = "Card Payment"
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
                    transaction_type=transaction_type,
                    foreign_amount=foreign_amount,
                    foreign_currency=foreign_currency,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=AmexTransactionsPipe))
