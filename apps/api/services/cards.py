from __future__ import annotations

import calendar
from datetime import date, datetime


def _d(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def next_due_date(due_day: int, today: date) -> date:
    """Next calendar date whose day-of-month is due_day (clamped for short months), today included."""
    def clamp(y: int, m: int) -> date:
        return date(y, m, min(due_day, calendar.monthrange(y, m)[1]))

    this = clamp(today.year, today.month)
    if this >= today:
        return this
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return clamp(y, m)


def latest_statement(statements: list[dict]) -> dict | None:
    return max(statements, key=lambda s: str(s["statement_date"]), default=None)


def outstanding(statement: dict | None) -> float:
    if not statement or statement.get("paid"):
        return 0.0
    return max(float(statement.get("total_due") or 0), 0.0)


def card_overview(card: dict, statements: list[dict], today: date) -> dict:
    last = latest_statement(statements)
    owed = outstanding(last)
    limit = card.get("credit_limit")
    if limit is None and last:
        limit = last.get("credit_limit")
    limit = float(limit) if limit is not None else None

    due = None
    if owed > 0 and last and last.get("due_date"):
        due_date, estimated = _d(last["due_date"]), False
    elif card.get("due_day"):
        due_date, estimated = next_due_date(int(card["due_day"]), today), True
    else:
        due_date, estimated = None, False
    if due_date:
        due = {
            "date": due_date.isoformat(),
            "days_left": (due_date - today).days,
            "overdue": owed > 0 and due_date < today,
            "estimated": estimated,
            "amount_due": round(owed, 2),
            "minimum_due": float(last["minimum_due"]) if owed > 0 and last and last.get("minimum_due") is not None else None,
        }

    return {
        "card": card,
        "credit_limit": limit,
        "outstanding": round(owed, 2),
        "available_credit": round(limit - owed, 2) if limit is not None else None,
        "utilization_pct": round(owed / limit * 100, 1) if limit else None,
        "last_statement": last,
        "next_due": due,
        "statement_count": len(statements),
    }


def upcoming_dues(overviews: list[dict], within_days: int = 30) -> list[dict]:
    """Cards that owe money, soonest (and overdue) first."""
    items = []
    for o in overviews:
        d = o["next_due"]
        if d and o["outstanding"] > 0 and d["days_left"] <= within_days:
            items.append({
                "card_id": o["card"]["id"],
                "label": f"{o['card']['bank_name']} ···· {o['card']['last4']}",
                **d,
            })
    return sorted(items, key=lambda x: x["days_left"])


def total_card_dues(cards_statements: dict[str, list[dict]]) -> float:
    """Net-worth liability: the latest statement's unpaid total for every card."""
    return round(sum(outstanding(latest_statement(s)) for s in cards_statements.values()), 2)
