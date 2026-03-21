from __future__ import annotations

import pytest

from context_use.providers.bank.barclays.pipe import (
    BankBarclaysPipe,
    _extract_transaction_type,
)
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.bank.conftest import BARCLAYS_CSV


class TestBankBarclaysPipe(PipeTestKit):
    pipe_class = BankBarclaysPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Transaction"

    @pytest.fixture()
    def pipe_fixture(self, tmp_path):
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/barclays/statement.csv"
        storage.write(key, BARCLAYS_CSV)
        return storage, key

    def test_money_out_has_negative_amount(self, extracted_records):
        debit = next(r for r in extracted_records if "Energy" in r.description)
        assert debit.amount.startswith("-")

    def test_money_in_has_positive_amount(self, extracted_records):
        credit = next(r for r in extracted_records if "Employer" in r.description)
        assert credit.amount.startswith("+")

    def test_transaction_type_extracted(self, extracted_records):
        dd = next(r for r in extracted_records if "Direct Debit" in r.description)
        assert dd.transaction_type == "Direct Debit"

    def test_card_purchase_type_extracted(self, extracted_records):
        cp = next(r for r in extracted_records if "Card Purchase" in r.description)
        assert cp.transaction_type == "Card Purchase"

    def test_preview_contains_institution(self, transformed_rows):
        for row in transformed_rows:
            assert "Barclays" in row.preview

    def test_empty_money_in_and_out_skipped(self, tmp_path):
        csv_with_empty = (
            b"Date,Description,Money Out,Money In,Balance\n"
            b"2025-11-01,Mystery Row,,,500.00\n"
            b"2025-11-02,Direct Debit to Energy Co,150.00,,350.00\n"
        )
        storage = DiskStorage(str(tmp_path / "store"))
        key = "archive/barclays/statement.csv"
        storage.write(key, csv_with_empty)
        pipe = BankBarclaysPipe()
        records = list(pipe.extract_file(key, storage))
        assert len(records) == 1
        assert "Energy" in records[0].description


class TestExtractTransactionType:
    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            ("Direct Debit to Skipton", "Direct Debit"),
            ("Card Purchase to Tesco", "Card Purchase"),
            ("Standing Order to MONZO", "Standing Order"),
            ("Bank Transfer from Someone", "Bank Transfer"),
            ("Cash Withdrawal at ATM", "Cash Withdrawal"),
            ("Cheque 001234", "Cheque"),
            ("Interest Payment", "Interest"),
            ("Random description", None),
            ("", None),
        ],
    )
    def test_extracts_type(self, description: str, expected: str | None) -> None:
        assert _extract_transaction_type(description) == expected
