from __future__ import annotations

import io
import json
import zipfile

import pytest
from pydantic import BaseModel

from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.providers.bank.generic_pipe import GenericBankPipe, _resolve_amount
from context_use.providers.bank.mapping import AmountColumns, BankMapping
from context_use.providers.bank.record import BankTransactionRecord
from context_use.storage.disk import DiskStorage
from context_use.testing import PipeTestKit

SINGLE_AMOUNT_CSV = (
    "Date,Description,Amount,Currency\n"
    "2026-01-15,Coffee Shop,-4.50,GBP\n"
    "2026-01-16,Salary,3000.00,GBP\n"
)

SPLIT_AMOUNT_CSV = (
    "Date,Description,Money In,Money Out,Balance\n"
    "2026-01-15,Coffee Shop,,4.50,100.00\n"
    "2026-01-16,Salary,3000.00,,3100.00\n"
)

CREDIT_CARD_CSV = (
    "Date,Description,Amount\n"
    "2026-01-15,Restaurant,25.00\n"
    "2026-01-16,Payment,-100.00\n"
)


def _make_mapping(
    *,
    single: str | None = "Amount",
    money_in: str | None = None,
    money_out: str | None = None,
    is_credit_card: bool = False,
    date_column: str = "Date",
    description_column: str = "Description",
) -> BankMapping:
    if single:
        amount = AmountColumns(single=single)
    else:
        amount = AmountColumns(money_in=money_in, money_out=money_out)
    return BankMapping(
        bank_name="TestBank",
        date_column=date_column,
        amount=amount,
        description_column=description_column,
        currency="GBP",
        is_credit_card=is_credit_card,
    )


def _make_task(key: str) -> EtlTask:
    return EtlTask(
        archive_id="a1",
        provider="bank",
        interaction_type="transaction",
        source_uris=[key],
        status=EtlTaskStatus.CREATED.value,
    )


class TestAmountColumns:
    def test_single_column(self) -> None:
        ac = AmountColumns(single="Amount")
        assert ac.single == "Amount"
        assert ac.money_in is None

    def test_split_columns(self) -> None:
        ac = AmountColumns(money_in="In", money_out="Out")
        assert ac.money_in == "In"
        assert ac.money_out == "Out"
        assert ac.single is None

    def test_neither_raises(self) -> None:
        with pytest.raises(ValueError, match="Specify either"):
            AmountColumns()

    def test_both_raises(self) -> None:
        with pytest.raises(ValueError, match="Specify either"):
            AmountColumns(single="Amount", money_in="In", money_out="Out")

    def test_partial_split_raises(self) -> None:
        with pytest.raises(ValueError, match="Both"):
            AmountColumns(money_in="In")


_SINGLE = AmountColumns(single="Amount")


class TestResolveAmount:
    def test_single_positive(self) -> None:
        row = {"Amount": "100.00"}
        result = _resolve_amount(row, _SINGLE, is_credit_card=False)
        assert result == "100.00"

    def test_single_negative(self) -> None:
        row = {"Amount": "-50.00"}
        result = _resolve_amount(row, _SINGLE, is_credit_card=False)
        assert result == "-50.00"

    def test_single_empty_returns_none(self) -> None:
        row = {"Amount": ""}
        result = _resolve_amount(row, _SINGLE, is_credit_card=False)
        assert result is None

    def test_credit_card_flips_sign(self) -> None:
        row = {"Amount": "25.00"}
        result = _resolve_amount(row, _SINGLE, is_credit_card=True)
        assert result == "-25.0"

    def test_credit_card_payment_becomes_positive(self) -> None:
        row = {"Amount": "-100.00"}
        result = _resolve_amount(row, _SINGLE, is_credit_card=True)
        assert result == "100.0"

    def test_split_money_out(self) -> None:
        cols = AmountColumns(money_in="In", money_out="Out")
        row = {"In": "", "Out": "4.50"}
        result = _resolve_amount(row, cols, is_credit_card=False)
        assert result == "-4.50"

    def test_split_money_in(self) -> None:
        cols = AmountColumns(money_in="In", money_out="Out")
        row = {"In": "3000.00", "Out": ""}
        result = _resolve_amount(row, cols, is_credit_card=False)
        assert result == "+3000.00"

    def test_split_both_empty_returns_none(self) -> None:
        cols = AmountColumns(money_in="In", money_out="Out")
        row = {"In": "", "Out": ""}
        result = _resolve_amount(row, cols, is_credit_card=False)
        assert result is None


class TestGenericBankPipeSingleAmount:
    @pytest.fixture()
    def storage_and_key(self, tmp_path: object) -> tuple[DiskStorage, str]:
        storage = DiskStorage(str(tmp_path))  # type: ignore[arg-type]
        key = "archive/bank/statement.csv"
        storage.write(key, SINGLE_AMOUNT_CSV.encode())
        return storage, key

    @pytest.fixture()
    def records(
        self, storage_and_key: tuple[DiskStorage, str]
    ) -> list[BankTransactionRecord]:
        storage, key = storage_and_key
        mapping = _make_mapping()
        pipe = GenericBankPipe(mapping=mapping)
        task = _make_task(key)
        return list(pipe.extract(task, storage))

    @pytest.fixture()
    def rows(self, storage_and_key: tuple[DiskStorage, str]) -> list[ThreadRow]:
        storage, key = storage_and_key
        mapping = _make_mapping()
        pipe = GenericBankPipe(mapping=mapping)
        task = _make_task(key)
        return list(pipe.run(task, storage))

    def test_extract_count(self, records: list[BankTransactionRecord]) -> None:
        assert len(records) == 2

    def test_amounts(self, records: list[BankTransactionRecord]) -> None:
        assert records[0].amount == "-4.50"
        assert records[1].amount == "3000.00"

    def test_descriptions(self, records: list[BankTransactionRecord]) -> None:
        assert records[0].description == "Coffee Shop"
        assert records[1].description == "Salary"

    def test_dates(self, records: list[BankTransactionRecord]) -> None:
        assert records[0].date == "2026-01-15"
        assert records[1].date == "2026-01-16"

    def test_transform_yields_thread_rows(self, rows: list[ThreadRow]) -> None:
        assert len(rows) == 2
        for row in rows:
            assert isinstance(row, ThreadRow)
            assert row.provider == "bank"
            assert row.payload["fibreKind"] == "Transaction"

    def test_preview_contains_bank_name(self, rows: list[ThreadRow]) -> None:
        for row in rows:
            assert "TestBank" in row.preview

    def test_spent_preview(self, rows: list[ThreadRow]) -> None:
        assert "Spent" in rows[0].preview
        assert "Coffee Shop" in rows[0].preview

    def test_source_preserved(self, records: list[BankTransactionRecord]) -> None:
        for r in records:
            assert r.source is not None
            parsed = json.loads(r.source)
            assert "Date" in parsed


class TestGenericBankPipeSplitAmount:
    @pytest.fixture()
    def records(self, tmp_path: object) -> list[BankTransactionRecord]:
        storage = DiskStorage(str(tmp_path))  # type: ignore[arg-type]
        key = "archive/bank/statement.csv"
        storage.write(key, SPLIT_AMOUNT_CSV.encode())
        mapping = _make_mapping(
            single=None, money_in="Money In", money_out="Money Out"
        )
        pipe = GenericBankPipe(mapping=mapping)
        task = _make_task(key)
        return list(pipe.extract(task, storage))

    def test_extract_count(self, records: list[BankTransactionRecord]) -> None:
        assert len(records) == 2

    def test_money_out_is_negative(self, records: list[BankTransactionRecord]) -> None:
        assert records[0].amount == "-4.50"

    def test_money_in_is_positive(self, records: list[BankTransactionRecord]) -> None:
        assert records[1].amount == "+3000.00"


class TestGenericBankPipeCreditCard:
    @pytest.fixture()
    def records(self, tmp_path: object) -> list[BankTransactionRecord]:
        storage = DiskStorage(str(tmp_path))  # type: ignore[arg-type]
        key = "archive/bank/statement.csv"
        storage.write(key, CREDIT_CARD_CSV.encode())
        mapping = _make_mapping(is_credit_card=True)
        pipe = GenericBankPipe(mapping=mapping)
        task = _make_task(key)
        return list(pipe.extract(task, storage))

    def test_charge_becomes_negative(
        self, records: list[BankTransactionRecord]
    ) -> None:
        assert records[0].amount == "-25.0"

    def test_payment_becomes_positive(
        self, records: list[BankTransactionRecord]
    ) -> None:
        assert records[1].amount == "100.0"


class TestGenericBankPipeNoMapping:
    def test_no_records_without_mapping(self, tmp_path: object) -> None:
        storage = DiskStorage(str(tmp_path))  # type: ignore[arg-type]
        key = "archive/bank/statement.csv"
        storage.write(key, SINGLE_AMOUNT_CSV.encode())
        pipe = GenericBankPipe()
        task = _make_task(key)
        rows = list(pipe.run(task, storage))
        assert rows == []
        assert pipe.error_count == 1


class TestReadCsvHeaders:
    def test_reads_headers_from_zip(self, tmp_path: object) -> None:
        from context_use.cli.bank_setup import _read_csv_headers

        zip_path = str(tmp_path) + "/test.zip"  # type: ignore[operator]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("bank/statement.csv", SINGLE_AMOUNT_CSV)
        with open(zip_path, "wb") as f:
            f.write(buf.getvalue())

        result = _read_csv_headers(zip_path)
        assert result is not None
        filename, headers = result
        assert filename == "bank/statement.csv"
        assert headers == ["Date", "Description", "Amount", "Currency"]

    def test_skips_macosx(self, tmp_path: object) -> None:
        from context_use.cli.bank_setup import _read_csv_headers

        zip_path = str(tmp_path) + "/test.zip"  # type: ignore[operator]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("__MACOSX/._statement.csv", "junk")
            zf.writestr("bank/statement.csv", SINGLE_AMOUNT_CSV)
        with open(zip_path, "wb") as f:
            f.write(buf.getvalue())

        result = _read_csv_headers(zip_path)
        assert result is not None
        assert result[0] == "bank/statement.csv"

    def test_no_csv_returns_none(self, tmp_path: object) -> None:
        from context_use.cli.bank_setup import _read_csv_headers

        zip_path = str(tmp_path) + "/test.zip"  # type: ignore[operator]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.json", "{}")
        with open(zip_path, "wb") as f:
            f.write(buf.getvalue())

        assert _read_csv_headers(zip_path) is None


_DEFAULT_MAPPING = _make_mapping()


class TestGenericBankPipeKit(PipeTestKit):
    """PipeTestKit conformance for GenericBankPipe."""

    pipe_class = GenericBankPipe
    expected_extract_count = 2
    expected_transform_count = 2
    expected_fibre_kind = "Transaction"
    per_record_interaction_type = True

    @pytest.fixture()
    def pipe_fixture(self, tmp_path: object) -> tuple[DiskStorage, str]:
        storage = DiskStorage(str(tmp_path))  # type: ignore[arg-type]
        key = "archive/bank/statement.csv"
        storage.write(key, SINGLE_AMOUNT_CSV.encode())
        return storage, key

    def _make_pipe(self) -> GenericBankPipe:
        return GenericBankPipe(mapping=_DEFAULT_MAPPING)

    @pytest.fixture()
    def extracted_records(
        self, pipe_fixture: tuple[DiskStorage, str]
    ) -> list[BaseModel]:
        storage, key = pipe_fixture
        pipe = self._make_pipe()
        task = _make_task(key)
        return list(pipe.extract(task, storage))

    @pytest.fixture()
    def transformed_rows(
        self, pipe_fixture: tuple[DiskStorage, str]
    ) -> list[ThreadRow]:
        storage, key = pipe_fixture
        pipe = self._make_pipe()
        task = _make_task(key)
        return list(pipe.run(task, storage))

    def test_counts_tracked(
        self, pipe_fixture: tuple[DiskStorage, str]
    ) -> None:
        storage, key = pipe_fixture
        pipe = self._make_pipe()
        task = _make_task(key)
        list(pipe.run(task, storage))
        assert pipe.extracted_count == self.expected_extract_count
        assert pipe.transformed_count == self.expected_transform_count
        assert pipe.error_count == 0

    def test_unique_keys_are_stable(
        self, pipe_fixture: tuple[DiskStorage, str]
    ) -> None:
        storage, key = pipe_fixture
        task = _make_task(key)
        first = [r.unique_key for r in self._make_pipe().run(task, storage)]
        second = [r.unique_key for r in self._make_pipe().run(task, storage)]
        assert first == second
