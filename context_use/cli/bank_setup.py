"""Interactive column-mapping setup for the generic bank provider.

Reads CSV headers from a zip archive and walks the user through mapping
columns to the fields required by :class:`BankMapping`.
"""

from __future__ import annotations

import csv
import io
import zipfile

from context_use.cli import output as out
from context_use.providers.bank.mapping import AmountColumns, BankMapping


def _read_csv_headers(zip_path: str) -> tuple[str, list[str]] | None:
    """Extract headers from the first CSV found inside *zip_path*.

    Returns ``(csv_filename, headers)`` or ``None`` if no CSV is found.
    """
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if name.startswith("__MACOSX"):
                continue
            if name.lower().endswith(".csv"):
                with zf.open(name) as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
                    try:
                        headers = next(reader)
                    except StopIteration:
                        continue
                    return name, [h.strip() for h in headers]
    return None


def _pick_column(headers: list[str], prompt_text: str) -> str | None:
    """Let the user pick one column by number."""
    choice = input(prompt_text).strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(headers):
            return headers[idx]
    except ValueError:
        pass
    out.error("Invalid choice.")
    return None


def _print_columns(headers: list[str]) -> None:
    for i, h in enumerate(headers, 1):
        print(f"  {out.bold(str(i))}. {h}")
    print()


def _ask_amount_columns(headers: list[str]) -> AmountColumns | None:
    """Ask whether amount is a single column or split into in/out."""
    out.header("Amount columns")
    print()
    print(f"  {out.bold('1')}. Single column (e.g. +100 / -50)")
    print(f"  {out.bold('2')}. Separate columns for money in / money out")
    print()

    mode = input("  Amount format? [1-2]: ").strip()

    if mode == "1":
        print()
        out.info("Which column contains the transaction amount?")
        print()
        _print_columns(headers)
        col = _pick_column(headers, f"  Amount column [1-{len(headers)}]: ")
        if col is None:
            return None
        return AmountColumns(single=col)

    if mode == "2":
        print()
        out.info("Which column contains money IN (credits/deposits)?")
        print()
        _print_columns(headers)
        col_in = _pick_column(headers, f"  Money-in column [1-{len(headers)}]: ")
        if col_in is None:
            return None

        print()
        out.info("Which column contains money OUT (debits/payments)?")
        print()
        _print_columns(headers)
        col_out = _pick_column(headers, f"  Money-out column [1-{len(headers)}]: ")
        if col_out is None:
            return None

        return AmountColumns(money_in=col_in, money_out=col_out)

    out.error("Invalid choice.")
    return None


def _ask_yes_no(prompt_text: str, *, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {prompt_text} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def run_bank_setup(zip_path: str) -> BankMapping | None:
    """Run the full interactive bank CSV setup.

    Returns a :class:`BankMapping` or ``None`` if the user aborts.
    """
    result = _read_csv_headers(zip_path)
    if result is None:
        out.error("No CSV files found in the archive.")
        return None

    csv_filename, headers = result
    if not headers:
        out.error(f"CSV file {csv_filename} has no columns.")
        return None

    out.header("Bank CSV setup")
    out.kv("File", csv_filename)
    print()

    out.info("CSV columns found:")
    print()
    _print_columns(headers)

    bank_name = input("  Bank name (e.g. Chase, HSBC): ").strip()
    if not bank_name:
        out.error("Bank name is required.")
        return None

    print()
    out.info("Which column contains the transaction date?")
    print()
    _print_columns(headers)
    date_col = _pick_column(headers, f"  Date column [1-{len(headers)}]: ")
    if date_col is None:
        return None

    print()
    amount = _ask_amount_columns(headers)
    if amount is None:
        return None

    print()
    out.info("Which column contains the transaction description?")
    print()
    _print_columns(headers)
    desc_col = _pick_column(headers, f"  Description column [1-{len(headers)}]: ")
    if desc_col is None:
        return None

    print()
    is_credit_card = _ask_yes_no(
        "Is this a credit card? (charges shown as positive amounts)"
    )

    print()
    currency = input("  Currency code (e.g. GBP, USD, EUR): ").strip().upper()
    if not currency:
        out.error("Currency is required.")
        return None

    print()
    out.header("Mapping summary")
    out.kv("Bank", bank_name)
    out.kv("Date column", date_col)
    if amount.single:
        out.kv("Amount column", amount.single)
    else:
        out.kv("Money-in column", amount.money_in)
        out.kv("Money-out column", amount.money_out)
    out.kv("Description column", desc_col)
    out.kv("Credit card", "yes" if is_credit_card else "no")
    out.kv("Currency", currency)
    print()

    if not _ask_yes_no("Proceed with this mapping?", default=True):
        out.warn("Aborted.")
        return None

    return BankMapping(
        bank_name=bank_name,
        date_column=date_col,
        amount=amount,
        description_column=desc_col,
        currency=currency,
        is_credit_card=is_credit_card,
    )
