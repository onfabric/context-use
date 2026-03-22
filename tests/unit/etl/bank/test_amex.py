from __future__ import annotations

import pytest

from context_use.providers.amex.transactions.pipe import AmexTransactionsPipe
from context_use.providers.bank.pipe import _parse_date
from context_use.providers.bank.transaction_types import normalize_transaction_type
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit
from tests.unit.etl.bank.conftest import AMEX_CSV


class TestAmexTransactionsPipe(PipeTestKit):
    pipe_class = AmexTransactionsPipe
    expected_extract_count = 3
    expected_transform_count = 3
    expected_fibre_kind = "Transaction"
    per_record_interaction_type = True

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

    def test_preview_contains_institution(self, transformed_rows):
        for row in transformed_rows:
            assert "Amex" in row.preview

    def test_provider_is_amex(self, transformed_rows):
        for row in transformed_rows:
            assert row.provider == "amex"

    def test_cr_row_interaction_type_is_payment(self, transformed_rows):
        payment = next(r for r in transformed_rows if "PAYMENT" in r.preview)
        assert payment.interaction_type == "payment"

    def test_debit_row_interaction_type_is_purchase(self, transformed_rows):
        debit = next(r for r in transformed_rows if "RESTAURANT" in r.preview)
        assert debit.interaction_type == "purchase"

    def test_transaction_type_set_on_records(self, extracted_records):
        for record in extracted_records:
            assert record.transaction_type is not None


class TestParseDate:
    def test_date_only(self) -> None:
        dt = _parse_date("2025-11-01")
        assert dt.year == 2025
        assert dt.month == 11
        assert dt.day == 1

    def test_datetime(self) -> None:
        dt = _parse_date("2025-11-01 14:30:00")
        assert dt.hour == 14

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse date"):
            _parse_date("not-a-date")


class TestNormalizeTransactionType:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Card Payment", "purchase"),
            ("Card Purchase", "purchase"),
            ("Direct Debit", "direct_debit"),
            ("Standing Order", "standing_order"),
            ("Transfer", "transfer"),
            ("Bank Transfer", "transfer"),
            ("Cash Withdrawal", "cash"),
            ("Cheque", "cheque"),
            ("Interest", "interest"),
            ("Payment", "payment"),
            ("Unknown Type", "transaction"),
            (None, "transaction"),
        ],
    )
    def test_normalizes(self, raw: str | None, expected: str) -> None:
        assert normalize_transaction_type(raw) == expected
