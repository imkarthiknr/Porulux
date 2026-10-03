from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

# Words that appear in many narrations but say nothing about who was paid.
_NOISE = {
    "upi", "neft", "imps", "rtgs", "ach", "nach", "pos", "ecs", "ref", "cr", "dr", "txn", "payment", "pay",
    "to", "from", "by", "via", "for", "the", "and", "bank", "ltd", "limited", "pvt", "private", "india",
    "debit", "credit", "card", "transfer", "mandate", "autopay", "si", "mob", "online", "bill", "icici",
    "hdfc", "sbi", "axis", "kotak", "paytm", "ybl", "oksbi", "okaxis", "okicici", "okhdfcbank", "apl",
}


def merchant_key(description: str) -> str:
    """Collapse 'UPI-NETFLIX-netflix@ybl-123456789' and 'UPI/NETFLIX/987654321' to 'netflix'."""
    text = re.sub(r"@\w+", " ", description.lower())
    tokens: list[str] = []
    for t in re.split(r"[^a-z]+", text):
        if len(t) >= 3 and t not in _NOISE and t not in tokens:  # UPI repeats the name as the handle
            tokens.append(t)
    return " ".join(tokens[:2])


@dataclass
class Recurring:
    name: str
    direction: str  # "expense" | "income"
    frequency: str  # "monthly" | "quarterly"
    typical_amount: float
    monthly_cost: float
    occurrences: int
    last_date: date
    next_expected: date
    variable: bool  # amount fluctuates (utilities, cards) rather than fixed (subscriptions, SIPs, EMIs)


def _frequency(gap_days: float) -> tuple[str, int] | None:
    if 25 <= gap_days <= 36:
        return "monthly", 1
    if 80 <= gap_days <= 100:
        return "quarterly", 3
    return None


def detect_recurring(txns: list[tuple[date, str, float]]) -> list[Recurring]:
    """txns are (date, description, signed_amount). A merchant counts as recurring when it shows up in
    at least 3 different months with a steady interval and a reasonably steady amount."""
    groups: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    for d, desc, amount in txns:
        key = merchant_key(desc)
        if not key or amount == 0:
            continue
        groups[(key, "income" if amount > 0 else "expense")].append((d, abs(amount)))

    found: list[Recurring] = []
    for (key, direction), rows in groups.items():
        rows.sort()
        # One payment per month at most: ignore repeats inside a month (e.g. many Swiggy orders).
        months = {(d.year, d.month) for d, _ in rows}
        if len(rows) < 3 or len(months) < 3:
            continue
        # Frequent small purchases at the same merchant (Swiggy, Uber) are habits, not subscriptions:
        # require roughly one hit per period.
        if len(rows) > len(months) * 1.5:
            continue
        gaps = [(b[0] - a[0]).days for a, b in zip(rows, rows[1:]) if (b[0] - a[0]).days > 5]
        if len(gaps) < 2:
            continue
        freq = _frequency(statistics.median(gaps))
        if not freq:
            continue
        amounts = [a for _, a in rows]
        median_amount = statistics.median(amounts)
        spread = max(abs(a - median_amount) for a in amounts) / median_amount if median_amount else 1
        if spread > 0.5:
            continue
        label, months_per_cycle = freq
        last = rows[-1][0]
        found.append(Recurring(
            name=key.title(),
            direction=direction,
            frequency=label,
            typical_amount=round(median_amount, 2),
            monthly_cost=round(median_amount / months_per_cycle, 2),
            occurrences=len(rows),
            last_date=last,
            next_expected=last + timedelta(days=round(statistics.median(gaps))),
            variable=spread > 0.1,
        ))
    found.sort(key=lambda r: (r.direction != "expense", -r.monthly_cost))
    return found
