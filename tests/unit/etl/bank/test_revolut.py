from __future__ import annotations

import pytest

from context_use.providers.bank.revolut.pipe import BankRevolutPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.bank.conftest import REVOLUT_CSV


class TestBankRevolutPipe(PipeTestKit):
    pipe_class = BankRevolutPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Transaction"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/revolut/account-statement.csv"
        storage.write(key, REVOLUT_CSV)
        return storage, key

    def test_reverted_rows_filtered(self, extracted_records):
        for record in extracted_records:
            assert "REVERTED" not in (record.source or "")

    def test_preview_contains_provider(self, transformed_rows):
        for row in transformed_rows:
            assert "Bank" in row.preview

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
