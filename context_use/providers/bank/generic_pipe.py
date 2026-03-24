from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator

from context_use.providers.bank.mapping import AmountColumns, BankMapping
from context_use.providers.bank.pipe import _BankTransactionPipe
from context_use.providers.bank.record import BankTransactionRecord
from context_use.providers.bank.transaction_types import FALLBACK_INTERACTION_TYPE
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

PROVIDER = "bank"


def _resolve_amount(
    raw_row: dict[str, str],
    amount_cfg: AmountColumns,
    *,
    is_credit_card: bool,
) -> str | None:
    """Derive a signed amount string from the CSV row.

    Returns ``None`` when the row has no usable amount (e.g. both
    money-in and money-out are empty).
    """
    if amount_cfg.single:
        raw = raw_row.get(amount_cfg.single, "").strip()
        if not raw:
            return None
        if is_credit_card:
            try:
                val = float(raw)
                return str(-val)
            except ValueError:
                return raw
        return raw

    assert amount_cfg.money_in is not None
    assert amount_cfg.money_out is not None
    money_in = raw_row.get(amount_cfg.money_in, "").strip()
    money_out = raw_row.get(amount_cfg.money_out, "").strip()
    if money_out:
        return f"-{money_out.lstrip('-')}"
    if money_in:
        return f"+{money_in.lstrip('+')}"
    return None


class GenericBankPipe(_BankTransactionPipe):
    provider = PROVIDER
    interaction_type = FALLBACK_INTERACTION_TYPE
    archive_version = 1
    archive_path_pattern = "*/bank/*.csv"
    display_name = "Bank"

    def __init__(self, mapping: BankMapping | None = None) -> None:
        super().__init__()
        self._mapping = mapping
        if mapping:
            self.display_name = mapping.bank_name

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[BankTransactionRecord]:
        if self._mapping is None:
            raise RuntimeError(
                "GenericBankPipe requires a BankMapping; "
                "use the interactive 'context-use ingest' flow to configure one."
            )
        mapping = self._mapping
        stream = storage.open_stream(source_uri)
        try:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
            for raw_row in reader:
                amount = _resolve_amount(
                    raw_row,
                    mapping.amount,
                    is_credit_card=mapping.is_credit_card,
                )
                if amount is None:
                    continue

                date = raw_row.get(mapping.date_column, "").strip()
                if not date:
                    continue

                description = raw_row.get(mapping.description_column, "").strip()

                yield BankTransactionRecord(
                    date=date,
                    amount=amount,
                    currency=mapping.currency,
                    description=description,
                    merchant_name=description or None,
                    source=json.dumps(raw_row),
                )
        finally:
            stream.close()


declare_interaction(InteractionConfig(pipe=GenericBankPipe))
