from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from services import ai
from services.ai import Credentials
from services.bank_import import ImportError_, parse_csv, parse_date

CARD_PROMPT = (
    "Extract this Indian credit card statement. Return ONLY a JSON object (no markdown, no explanation):\n"
    '{"card_last4":"<last 4 digits or null>","statement_date":"YYYY-MM-DD","period_start":"YYYY-MM-DD or null",'
    '"period_end":"YYYY-MM-DD or null","due_date":"YYYY-MM-DD or null","total_due":<number>,'
    '"minimum_due":<number or null>,"credit_limit":<number or null>,'
    '"transactions":[{"date":"YYYY-MM-DD","description":"<merchant/narration>","amount":<number>}]}\n'
    "All amounts are plain INR numbers. total_due is the 'Total Amount Due' to pay. In transactions, amount is "
    "POSITIVE for purchases, fees, taxes and interest charged, and NEGATIVE for payments received, refunds and "
    "reversals. Include every transaction line; skip balance/summary rows."
)


@dataclass
class CardTxn:
    txn_date: date
    description: str
    amount: float  # positive = you owe more; negative = payment/refund


@dataclass
class ParsedStatement:
    statement_date: date
    period_start: date | None
    period_end: date | None
    due_date: date | None
    total_due: float
    minimum_due: float | None
    credit_limit: float | None
    card_last4: str | None
    transactions: list[CardTxn]
    source: str


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def normalize_ai_result(raw: dict) -> ParsedStatement:
    """Validate/clean what the model returned. Raises ValueError when it is unusable."""
    stmt_date = parse_date(str(raw.get("statement_date") or "")) or parse_date(str(raw.get("period_end") or ""))
    total = _num(raw.get("total_due"))
    if stmt_date is None or total is None:
        raise ValueError("statement date or total due missing")
    txns: list[CardTxn] = []
    for t in raw.get("transactions") or []:
        d, desc, amt = parse_date(str(t.get("date") or "")), str(t.get("description") or "").strip(), _num(t.get("amount"))
        if d and desc and amt:
            txns.append(CardTxn(d, desc, round(amt, 2)))
    digits = "".join(ch for ch in str(raw.get("card_last4") or "") if ch.isdigit())
    return ParsedStatement(
        statement_date=stmt_date,
        period_start=parse_date(str(raw.get("period_start") or "")),
        period_end=parse_date(str(raw.get("period_end") or "")),
        due_date=parse_date(str(raw.get("due_date") or "")),
        total_due=round(total, 2),
        minimum_due=_num(raw.get("minimum_due")),
        credit_limit=_num(raw.get("credit_limit")),
        card_last4=digits[-4:] if len(digits) >= 4 else None,
        transactions=txns,
        source="upload",
    )


def parse_card_csv(content: bytes) -> ParsedStatement:
    """CSV exports carry no due date or minimum due, so the statement is synthesised from the rows:
    bank CSVs record purchases as debits (negative), which for a card means money owed."""
    rows = parse_csv(content)  # raises ImportError_
    txns = [CardTxn(r.transaction_date, r.description, round(-r.amount, 2)) for r in rows]
    dates = [t.txn_date for t in txns]
    owed = max(sum(t.amount for t in txns), 0.0)
    return ParsedStatement(
        statement_date=max(dates), period_start=min(dates), period_end=max(dates), due_date=None,
        total_due=round(owed, 2), minimum_due=None, credit_limit=None, card_last4=None,
        transactions=txns, source="csv",
    )


async def extract_card_statement(data: bytes, media_type: str, *, creds: Credentials) -> ParsedStatement:
    raw = await ai.generate(data, media_type, CARD_PROMPT, creds=creds, max_tokens=32000)
    parsed = ai.parse_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return normalize_ai_result(parsed)


__all__ = ["ParsedStatement", "CardTxn", "parse_card_csv", "extract_card_statement", "normalize_ai_result", "ImportError_"]
