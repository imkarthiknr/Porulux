from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

DATE_FORMATS = (
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d",
    "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y", "%d.%m.%Y",
)

_DATE_HEADERS = ("date", "txn date", "transaction date", "value date")
_DESC_HEADERS = ("narration", "description", "particulars", "remarks", "transaction remarks", "details")
_DEBIT_HEADERS = ("debit", "withdrawal", "withdrawal amt", "withdrawal amount", "dr", "debit amount")
_CREDIT_HEADERS = ("credit", "deposit", "deposit amt", "deposit amount", "cr", "credit amount")
_AMOUNT_HEADERS = ("amount",)
_TYPE_HEADERS = ("dr/cr", "cr/dr", "type", "transaction type")


class ImportError_(ValueError):
    """Raised when a statement can't be parsed."""


@dataclass
class ParsedTransaction:
    transaction_date: date
    description: str
    amount: float  # positive = credit, negative = debit


def parse_date(s: str) -> date | None:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(s: str | None) -> float | None:
    if s is None:
        return None
    s = re.sub(r"[₹,\s]|INR|Rs\.?", "", s, flags=re.IGNORECASE)
    if not s or s in ("-", "--"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    suffix = None
    if s[-2:].upper() in ("DR", "CR"):
        suffix, s = s[-2:].upper(), s[:-2]
    try:
        value = float(s)
    except ValueError:
        return None
    if negative or suffix == "DR":
        value = -abs(value)
    return value


def _norm(c: str) -> str:
    return re.sub(r"\s+", " ", c.replace(".", "")).strip().lower()


def _find(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    for c in candidates:
        if c in headers:
            return headers.index(c)
    return None


def parse_csv(content: bytes) -> list[ParsedTransaction]:
    """Parse a bank statement CSV. Tolerates preamble rows above the header,
    separate debit/credit columns or a single signed amount column."""
    text = content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))

    header_idx = None
    for i, row in enumerate(rows):
        lowered = [_norm(c) for c in row]
        if _find(lowered, _DATE_HEADERS) is not None and _find(lowered, _DESC_HEADERS) is not None:
            header_idx = i
            break
    if header_idx is None:
        raise ImportError_("Could not find a header row with date and description columns.")

    headers = [_norm(c) for c in rows[header_idx]]
    i_date = _find(headers, _DATE_HEADERS)
    i_desc = _find(headers, _DESC_HEADERS)
    i_debit = _find(headers, _DEBIT_HEADERS)
    i_credit = _find(headers, _CREDIT_HEADERS)
    i_amount = _find(headers, _AMOUNT_HEADERS)
    i_type = _find(headers, _TYPE_HEADERS)
    if i_debit is None and i_credit is None and i_amount is None:
        raise ImportError_("Could not find debit/credit or amount columns.")

    def cell(row: list[str], idx: int | None) -> str | None:
        return row[idx] if idx is not None and idx < len(row) else None

    out: list[ParsedTransaction] = []
    for row in rows[header_idx + 1:]:
        d = parse_date(cell(row, i_date) or "")
        if d is None:
            continue  # footers, blank lines, wrapped narration rows
        desc = (cell(row, i_desc) or "").strip()
        if not desc:
            continue

        amount: float | None = None
        if i_debit is not None or i_credit is not None:
            debit = parse_amount(cell(row, i_debit))
            credit = parse_amount(cell(row, i_credit))
            if debit:
                amount = -abs(debit)
            elif credit:
                amount = abs(credit)
        else:
            amount = parse_amount(cell(row, i_amount))
            kind = (cell(row, i_type) or "").strip().lower()
            if amount is not None and kind in ("dr", "debit", "d"):
                amount = -abs(amount)
            elif amount is not None and kind in ("cr", "credit", "c"):
                amount = abs(amount)
        if amount is None or amount == 0:
            continue
        out.append(ParsedTransaction(d, desc, round(amount, 2)))

    if not out:
        raise ImportError_("No transactions found in the file.")
    return out
