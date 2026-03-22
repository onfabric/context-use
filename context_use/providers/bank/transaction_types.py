from __future__ import annotations

_TRANSACTION_TYPE_MAP: dict[str, str] = {
    "Card Payment": "purchase",
    "Card Purchase": "purchase",
    "Direct Debit": "direct_debit",
    "Standing Order": "standing_order",
    "Transfer": "transfer",
    "Bank Transfer": "transfer",
    "Cash Withdrawal": "cash",
    "Cheque": "cheque",
    "Interest": "interest",
    "Payment": "payment",
}

FALLBACK_INTERACTION_TYPE = "transaction"


def normalize_transaction_type(raw: str | None) -> str:
    if raw is None:
        return FALLBACK_INTERACTION_TYPE
    return _TRANSACTION_TYPE_MAP.get(raw, FALLBACK_INTERACTION_TYPE)
