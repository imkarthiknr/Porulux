from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from services import ai
from services.ai import Credentials
from services.bank_import import ImportError_, parse_csv, parse_date

KINDS = ("disbursement", "emi", "prepayment", "interest", "principal", "charge", "other")

LOAN_PROMPT = (
    "Extract this Indian loan account statement (home, personal, vehicle or other term loan). Return ONLY a JSON "
    "object (no markdown, no explanation):\n"
    '{"statement_date":"YYYY-MM-DD","period_start":"YYYY-MM-DD or null","period_end":"YYYY-MM-DD or null",'
    '"opening_balance":<outstanding principal at start or null>,"closing_balance":<outstanding principal at end or null>,'
    '"transactions":[{"date":"YYYY-MM-DD","description":"<narration>","kind":"disbursement|emi|prepayment|interest|principal|charge|other",'
    '"amount":<number>,"principal":<number or null>,"interest":<number or null>,"charges":<number or null>,'
    '"balance":<outstanding principal after this line, or null>}]}\n'
    "All amounts are plain positive INR numbers. kind: disbursement = loan amount paid out; emi = an instalment paid; "
    "prepayment = part-payment or foreclosure; interest or principal = a line that is only that component; charge = "
    "fees, penalties, GST, insurance. amount is the full value of the line. For an emi line, fill principal and "
    "interest when the statement splits them (principal + interest = amount, any fee goes in charges). If the "
    "statement shows an instalment's components as separate lines, give those lines kind interest and principal and "
    "do NOT also emit a combined emi line for the same payment. balance is the outstanding principal, not the "
    "next EMI or total dues. Include every transaction line in statement order; skip summary rows."
)

# Checked in this order: "EMI bounce charges" is a charge, "GST on interest" is a charge.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("disbursement", ("disburs",)),
    ("prepayment", ("prepay", "part pay", "part-pay", "partpay", "foreclos", "lump sum", "lumpsum")),
    ("charge", ("charge", "fee", "gst", "penal", "bounce", "stamp", "insurance", "premium")),
    ("emi", ("emi", "instal", "repayment")),
    ("interest", ("interest",)),
    ("principal", ("principal",)),
]


def classify(description: str) -> str:
    text = description.lower()
    for kind, words in _KEYWORDS:
        if any(w in text for w in words):
            return kind
    return "other"


@dataclass
class LoanTxn:
    txn_date: date
    description: str
    kind: str
    amount: float
    principal: float | None = None
    interest: float | None = None
    charges: float | None = None
    balance: float | None = None


@dataclass
class ParsedLoanStatement:
    statement_date: date
    period_start: date | None
    period_end: date | None
    opening_balance: float | None
    closing_balance: float | None
    transactions: list[LoanTxn]
    source: str


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pos(v) -> float | None:
    n = _num(v)
    return round(abs(n), 2) if n is not None else None


def fill_components(txns: list[LoanTxn], opening_balance: float | None) -> None:
    """Work out principal/interest/charges for every line, in place.

    Lines already carry them when the statement splits an EMI. Otherwise the outstanding balance gives it away:
    the drop in balance across an EMI is the principal repaid, and the rest of the EMI is interest."""
    prev = opening_balance
    for t in txns:
        if t.kind == "prepayment":
            t.principal = t.principal if t.principal is not None else t.amount
        elif t.kind == "principal":
            t.principal = t.amount
        elif t.kind == "interest":
            t.interest = t.amount
        elif t.kind == "charge":
            t.charges = t.charges if t.charges is not None else t.amount
        elif t.kind == "emi" and t.principal is None and t.interest is None:
            if t.balance is not None and prev is not None:
                principal = round(prev - t.balance, 2)
                if -0.01 <= principal <= t.amount + 0.01:
                    principal = min(max(principal, 0.0), t.amount)
                    t.principal, t.interest = principal, round(t.amount - principal, 2)
        elif t.kind == "emi":
            # Only one component given: the other is whatever is left of the instalment.
            fees = t.charges or 0.0
            if t.principal is None:
                t.principal = round(max(t.amount - (t.interest or 0.0) - fees, 0.0), 2)
            elif t.interest is None:
                t.interest = round(max(t.amount - t.principal - fees, 0.0), 2)
        if t.balance is not None:
            prev = t.balance
        elif t.kind == "disbursement" and prev is not None:
            prev = round(prev + t.amount, 2)


def normalize_ai_result(raw: dict) -> ParsedLoanStatement:
    """Validate/clean what the model returned. Raises ValueError when it is unusable."""
    txns: list[LoanTxn] = []
    for t in raw.get("transactions") or []:
        d, desc, amt = parse_date(str(t.get("date") or "")), str(t.get("description") or "").strip(), _pos(t.get("amount"))
        if not (d and desc and amt):
            continue
        kind = str(t.get("kind") or "").lower()
        if kind not in KINDS:
            kind = classify(desc)
        txns.append(LoanTxn(d, desc, kind, amt, _pos(t.get("principal")), _pos(t.get("interest")), _pos(t.get("charges")), _pos(t.get("balance"))))
    stmt_date = (
        parse_date(str(raw.get("statement_date") or ""))
        or parse_date(str(raw.get("period_end") or ""))
        or (max(t.txn_date for t in txns) if txns else None)
    )
    if stmt_date is None or not txns:
        raise ValueError("no transactions or statement date found")
    opening = _num(raw.get("opening_balance"))
    fill_components(txns, opening)
    closing = _num(raw.get("closing_balance"))
    if closing is None:
        closing = next((t.balance for t in reversed(txns) if t.balance is not None), None)
    return ParsedLoanStatement(
        statement_date=stmt_date,
        period_start=parse_date(str(raw.get("period_start") or "")),
        period_end=parse_date(str(raw.get("period_end") or "")),
        opening_balance=opening,
        closing_balance=closing,
        transactions=txns,
        source="upload",
    )


def parse_loan_csv(content: bytes) -> ParsedLoanStatement:
    """CSV exports have no explicit kind, so it comes from the narration. Debit/credit direction is not
    trusted (it differs between lenders); the running balance does the principal/interest split."""
    rows = parse_csv(content)  # raises ImportError_
    txns = [LoanTxn(r.transaction_date, r.description, classify(r.description), round(abs(r.amount), 2), balance=r.balance) for r in rows]
    txns = [t for t in txns if t.amount]
    if not txns:
        raise ImportError_("No transactions found in this file.")
    fill_components(txns, None)  # no opening balance in a CSV, so the first EMI can't be split from balances
    dates = [t.txn_date for t in txns]
    closing = next((t.balance for t in reversed(txns) if t.balance is not None), None)
    return ParsedLoanStatement(max(dates), min(dates), max(dates), None, closing, txns, "csv")


async def extract_loan_statement(data: bytes, media_type: str, *, creds: Credentials) -> ParsedLoanStatement:
    raw = await ai.generate(data, media_type, LOAN_PROMPT, creds=creds, max_tokens=32000)
    parsed = ai.parse_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return normalize_ai_result(parsed)


def summarize_account(txns: list[dict], statements: list[dict], loan: dict | None = None) -> dict:
    """Totals over everything imported so far. `txns` are loan_transactions rows."""
    ordered = sorted(txns, key=lambda t: (t["txn_date"], t.get("line_no") or 0))

    def total(key: str, kinds: tuple[str, ...] | None = None) -> float:
        return round(sum(float(t[key] or 0) for t in ordered if t.get(key) is not None and (kinds is None or t["kind"] in kinds)), 2)

    emis = [t for t in ordered if t["kind"] == "emi"]
    unsplit = [t for t in emis if t.get("principal_amount") is None and t.get("interest_amount") is None]

    balance, as_of = None, None
    for t in reversed(ordered):
        if t.get("balance_after") is not None:
            balance, as_of = float(t["balance_after"]), t["txn_date"]
            break
    if balance is None and statements:
        latest = max((s for s in statements if s.get("closing_balance") is not None), key=lambda s: s["statement_date"], default=None)
        if latest:
            balance, as_of = float(latest["closing_balance"]), latest["statement_date"]

    repaid = ("emi", "prepayment", "interest", "principal", "charge")
    return {
        "interest_paid": total("interest_amount"),
        "principal_paid": total("principal_amount"),
        "charges_paid": total("charges_amount"),
        "total_paid": round(sum(float(t["amount"]) for t in ordered if t["kind"] in repaid), 2),
        "disbursed": total("amount", ("disbursement",)),
        "prepaid": total("amount", ("prepayment",)),
        "balance": balance,
        "balance_as_of": as_of,
        "emis_paid": len(emis),
        "unsplit_emis": len(unsplit),
        "transaction_count": len(ordered),
        "first_date": ordered[0]["txn_date"] if ordered else None,
        "last_date": ordered[-1]["txn_date"] if ordered else None,
    }


__all__ = [
    "LoanTxn", "ParsedLoanStatement", "classify", "fill_components", "normalize_ai_result", "parse_loan_csv",
    "extract_loan_statement", "summarize_account", "ImportError_",
]
