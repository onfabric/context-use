from __future__ import annotations

import pytest

from context_use.providers.revolut.transactions.pipe import (
    RevolutTransactionsPipe,
    _parse_revolut_date,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.bank.conftest import REVOLUT_CSV


class TestRevolutTransactionsPipe(PipeTestKit):
    pipe_class = RevolutTransactionsPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Transaction"
    per_record_interaction_type = True

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/revolut/account-statement.csv"
        storage.write(key, REVOLUT_CSV)
        return storage, key

    def test_reverted_rows_filtered(self, extracted_records):
        for record in extracted_records:
            assert "REVERTED" not in (record.source or "")

    def test_preview_contains_institution(self, transformed_rows):
        for row in transformed_rows:
            assert "Revolut" in row.preview

    def test_provider_is_revolut(self, transformed_rows):
        for row in transformed_rows:
            assert row.provider == "revolut"

    def test_transfer_has_positive_amount(self, extracted_records):
        transfer = next(
            r for r in extracted_records if r.transaction_type == "Transfer"
        )
        assert not transfer.amount.startswith("-")

    def test_card_payment_has_negative_amount(self, extracted_records):
        card = next(
            r for r in extracted_records if r.transaction_type == "Card Payment"
        )
        assert card.amount.startswith("-")

    def test_transfer_interaction_type(self, transformed_rows):
        xfer = next(r for r in transformed_rows if "From GBP" in r.preview)
        assert xfer.interaction_type == "transfer"

    def test_purchase_interaction_type(self, transformed_rows):
        card = next(r for r in transformed_rows if "Coffee" in r.preview)
        assert card.interaction_type == "purchase"


class TestParseRevolutDate:
    def test_valid_datetime(self) -> None:
        assert _parse_revolut_date("2025-11-01 10:00:00") == "2025-11-01"

    def test_valid_date_only(self) -> None:
        assert _parse_revolut_date("2025-11-01") == "2025-11-01"

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse Revolut date"):
            _parse_revolut_date("not-a-date")
