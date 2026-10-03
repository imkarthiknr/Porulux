from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

SECTION_24B_LIMIT = 200_000   # self-occupied home loan interest, old tax regime
SECTION_80C_LIMIT = 150_000   # principal repayment shares this ceiling with PF, ELSS, insurance, etc.


def add_months(d: date, months: int) -> date:
    idx = d.month - 1 + months
    year, month = d.year + idx // 12, idx % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def fy_label(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def emi_for(principal: float, annual_pct: float, months: int) -> float:
    r = annual_pct / 1200
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def principal_for(emi: float, annual_pct: float, months: int) -> float:
    r = annual_pct / 1200
    if r == 0:
        return emi * months
    return emi * (1 - (1 + r) ** -months) / r


@dataclass
class Instalment:
    number: int
    due_date: date
    opening: float
    interest: float
    principal: float
    closing: float

    @property
    def emi(self) -> float:
        return self.interest + self.principal


def build_schedule(
    *, principal: float | None, annual_pct: float, emi: float | None, tenure_months: int, start_date: date
) -> list[Instalment]:
    """Standard reducing-balance schedule; the first EMI falls one month after start_date.
    Give principal or emi (the other is derived) plus rate and tenure."""
    if principal is None and emi is None:
        raise ValueError("Need the original loan amount or the EMI")
    if tenure_months <= 0:
        raise ValueError("Need the loan tenure in months")
    if principal is None:
        principal = principal_for(emi, annual_pct, tenure_months)
    if emi is None:
        emi = emi_for(principal, annual_pct, tenure_months)

    r = annual_pct / 1200
    balance, rows = principal, []
    for n in range(1, tenure_months + 1):
        interest = balance * r
        paid_principal = min(emi - interest, balance)
        if paid_principal <= 0:
            raise ValueError("EMI does not cover the monthly interest; check rate, EMI and amount")
        closing = balance - paid_principal
        if n == tenure_months or closing < 0.5:
            paid_principal, closing = balance, 0.0   # final instalment clears any rounding drift
        rows.append(Instalment(n, add_months(start_date, n), round(balance, 2), round(interest, 2), round(paid_principal, 2), round(closing, 2)))
        balance = closing
        if closing == 0:
            break
    return rows


def summarize(schedule: list[Instalment], today: date) -> dict:
    paid = [i for i in schedule if i.due_date <= today]
    per_fy: dict[str, dict[str, float]] = {}
    for i in schedule:
        fy = per_fy.setdefault(fy_label(i.due_date), {"interest": 0.0, "principal": 0.0, "emis": 0})
        fy["interest"] += i.interest
        fy["principal"] += i.principal
        fy["emis"] += 1
    tax = []
    for fy, v in sorted(per_fy.items()):
        tax.append({
            "financial_year": fy,
            "interest": round(v["interest"], 2),
            "principal": round(v["principal"], 2),
            "emis": v["emis"],
            "deduction_24b": round(min(v["interest"], SECTION_24B_LIMIT), 2),
            "deduction_80c_principal": round(min(v["principal"], SECTION_80C_LIMIT), 2),
        })
    first = schedule[0].opening if schedule else 0.0
    return {
        "original_principal": round(first, 2),
        "emi": round(schedule[0].emi, 2) if schedule else 0.0,
        "emis_paid": len(paid),
        "emis_remaining": len(schedule) - len(paid),
        "interest_paid_to_date": round(sum(i.interest for i in paid), 2),
        "principal_paid_to_date": round(sum(i.principal for i in paid), 2),
        "outstanding_principal": round(paid[-1].closing if paid else first, 2),
        "total_interest": round(sum(i.interest for i in schedule), 2),
        "payoff_date": schedule[-1].due_date.isoformat() if schedule else None,
        "tax_by_year": tax,
        "current_financial_year": fy_label(today),
    }
