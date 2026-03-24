from __future__ import annotations

from pydantic import BaseModel


class BankTransactionRecord(BaseModel):
    date: str
    authorized_date: str | None = None
    amount: str
    currency: str
    description: str
    merchant_name: str | None = None
    transaction_type: str | None = None
    payment_channel: str | None = None
    pending: bool = False
    account_owner: str | None = None
    foreign_amount: str | None = None
    foreign_currency: str | None = None
    source: str | None = None
