from __future__ import annotations

import pytest

from context_use.providers.bank.amex.pipe import BankAmexPipe
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.bank.conftest import AMEX_CSV


class TestBankAmexPipe(PipeTestKit):
    pipe_class = BankAmexPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Transaction"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/amex/statement.csv"
        storage.write(key, AMEX_CSV)
        return storage, key

    def test_cr_row_has_positive_amount(self, extracted_records):
        payment = next(r for r in extracted_records if "PAYMENT" in r.description)
        assert payment.amount.startswith("+")

    def test_debit_row_has_negative_amount(self, extracted_records):
        debit = next(r for r in extracted_records if "RESTAURANT" in r.description)
        assert debit.amount.startswith("-")

    def test_account_owner_set(self, extracted_records):
        for record in extracted_records:
            assert record.account_owner is not None

    def test_foreign_currency_populated(self, extracted_records):
        foreign = next(r for r in extracted_records if r.foreign_currency is not None)
        assert foreign.foreign_currency == "USD"
        assert foreign.foreign_amount == "12.50"

    def test_preview_shows_account_owner(self, transformed_rows):
        for row in transformed_rows:
            assert "(by " in row.preview
