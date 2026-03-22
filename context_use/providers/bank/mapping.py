from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AmountColumns:
    """Describes how to read the transaction amount from a CSV row.

    Either a single column with signed values, or separate columns for
    money in / money out.
    """

    single: str | None = None
    money_in: str | None = None
    money_out: str | None = None

    def __post_init__(self) -> None:
        has_single = self.single is not None
        has_split = self.money_in is not None or self.money_out is not None
        if has_single == has_split:
            raise ValueError(
                "Specify either 'single' or 'money_in'/'money_out', not both"
            )
        if has_split and (self.money_in is None or self.money_out is None):
            raise ValueError(
                "Both 'money_in' and 'money_out' must be provided together"
            )


@dataclass(frozen=True)
class BankMapping:
    """Runtime configuration for the generic bank CSV pipe.

    Captures the user's interactive column-mapping choices so
    ``GenericBankPipe`` can extract ``BankTransactionRecord`` from any CSV.
    """

    bank_name: str
    date_column: str
    amount: AmountColumns
    description_column: str
    currency: str
    is_credit_card: bool = False
