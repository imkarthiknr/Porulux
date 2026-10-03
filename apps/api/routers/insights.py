from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.supabase import get_supabase_client
from services.loan_math import build_schedule, summarize
from services.recurring import detect_recurring
from services.xirr import xirr

OPENING_BALANCE = "Opening Balance"

router = APIRouter(prefix="/api/v1", tags=["insights"])


def _first_of_month(d: date, back: int = 0) -> date:
    idx = d.year * 12 + d.month - 1 - back
    return date(idx // 12, idx % 12 + 1, 1)


def _fetch_txns(user_id: str, since: date) -> list[dict]:
    return (
        get_supabase_client().table("bank_transactions")
        .select("transaction_date,description,amount,category")
        .eq("user_id", user_id).gte("transaction_date", since.isoformat())
        .limit(10000).execute()
    ).data


# ── Spend trend ───────────────────────────────────────────────────────────────

@router.get("/transactions/trend")
async def spend_trend(months: int = Query(6, ge=2, le=24), user_id: str = Depends(get_current_user)):
    """Income vs expenses per month plus per-category spend, for the last `months` months."""
    today = date.today()
    start = _first_of_month(today, months - 1)
    rows = [r for r in _fetch_txns(user_id, start) if r["category"] != OPENING_BALANCE]

    buckets = {_first_of_month(today, months - 1 - i).strftime("%Y-%m"): {"income": 0.0, "expenses": 0.0, "cats": defaultdict(float)} for i in range(months)}
    for r in rows:
        b = buckets.get(r["transaction_date"][:7])
        if b is None:
            continue
        if r["amount"] > 0:
            b["income"] += r["amount"]
        else:
            b["expenses"] += -r["amount"]
            b["cats"][r["category"] or "Other"] += -r["amount"]

    totals: dict[str, float] = defaultdict(float)
    for b in buckets.values():
        for c, v in b["cats"].items():
            totals[c] += v
    top = [c for c, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:5]]

    series = []
    for month, b in buckets.items():
        other = sum(v for c, v in b["cats"].items() if c not in top)
        series.append({
            "month": month,
            "income": round(b["income"], 2),
            "expenses": round(b["expenses"], 2),
            "net": round(b["income"] - b["expenses"], 2),
            "categories": {**{c: round(b["cats"].get(c, 0.0), 2) for c in top}, **({"Other": round(other, 2)} if other else {})},
        })
    spend = [s["expenses"] for s in series if s["expenses"] > 0]
    return {
        "months": series,
        "top_categories": top + (["Other"] if any("Other" in s["categories"] for s in series) and "Other" not in top else []),
        "average_monthly_spend": round(sum(spend) / len(spend), 2) if spend else 0.0,
    }


# ── Recurring payments ────────────────────────────────────────────────────────

@router.get("/transactions/recurring")
async def recurring_payments(user_id: str = Depends(get_current_user)):
    since = _first_of_month(date.today(), 12)
    txns = [
        (date.fromisoformat(r["transaction_date"]), r["description"], float(r["amount"]))
        for r in _fetch_txns(user_id, since) if r["category"] != OPENING_BALANCE
    ]
    items = detect_recurring(txns)
    expenses = [i for i in items if i.direction == "expense"]
    return {
        "items": [
            {**i.__dict__, "last_date": i.last_date.isoformat(), "next_expected": i.next_expected.isoformat()}
            for i in items
        ],
        "monthly_commitments": round(sum(i.monthly_cost for i in expenses), 2),
    }


# ── Investments: lots and returns (XIRR) ──────────────────────────────────────

class LotCreate(BaseModel):
    lot_date: date
    lot_type: str = Field("BUY", pattern="^(BUY|SELL)$")
    units: float = Field(..., gt=0)
    price: float = Field(..., ge=0)


def _own_holding(user_id: str, holding_id: str) -> dict:
    rows = (
        get_supabase_client().table("holdings").select("id").eq("id", holding_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return rows[0]


@router.get("/holdings/{holding_id}/lots")
async def list_lots(holding_id: str, user_id: str = Depends(get_current_user)):
    _own_holding(user_id, holding_id)
    return (
        get_supabase_client().table("holding_lots").select("*")
        .eq("holding_id", holding_id).eq("user_id", user_id).order("lot_date", desc=False).execute()
    ).data


@router.post("/holdings/{holding_id}/lots", status_code=status.HTTP_201_CREATED)
async def add_lot(holding_id: str, payload: LotCreate, user_id: str = Depends(get_current_user)):
    _own_holding(user_id, holding_id)
    row = {**payload.model_dump(mode="json"), "holding_id": holding_id, "user_id": user_id}
    return get_supabase_client().table("holding_lots").insert(row).execute().data[0]


@router.delete("/lots/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lot(lot_id: str, user_id: str = Depends(get_current_user)):
    res = get_supabase_client().table("holding_lots").delete().eq("id", lot_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lot not found")


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 2)


@router.get("/investments/returns")
async def investment_returns(user_id: str = Depends(get_current_user)):
    client = get_supabase_client()
    holdings = client.table("holdings").select("*").eq("user_id", user_id).execute().data
    lots = client.table("holding_lots").select("*").eq("user_id", user_id).execute().data
    by_holding: dict[str, list[dict]] = defaultdict(list)
    for lot in lots:
        by_holding[lot["holding_id"]].append(lot)

    today = date.today()
    out, portfolio_flows = [], []
    total_cost = total_value = 0.0
    for h in holdings:
        hl = by_holding.get(h["id"], [])
        price = float(h["current_price"]) if h.get("current_price") is not None else None
        if hl:
            net_units = sum(float(l["units"]) * (1 if l["lot_type"] == "BUY" else -1) for l in hl)
            units = float(h["units"]) if float(h["units"] or 0) > 0 else net_units
            cost = sum(float(l["units"]) * float(l["price"]) * (1 if l["lot_type"] == "BUY" else -1) for l in hl)
        else:
            units = float(h["units"] or 0)
            cost = units * float(h["avg_buy_price"]) if h.get("avg_buy_price") is not None else None
        value = units * price if price is not None else None

        flows = [
            (date.fromisoformat(l["lot_date"]), -float(l["units"]) * float(l["price"]) * (1 if l["lot_type"] == "BUY" else -1))
            for l in hl
        ]
        rate = None
        if flows and value is not None and value > 0:
            rate = xirr(flows + [(today, value)])
            portfolio_flows += flows + [(today, value)]

        if cost is not None and value is not None:
            total_cost += cost
            total_value += value
        out.append({
            "holding_id": h["id"], "symbol": h["symbol"], "name": h["name"], "holding_type": h["holding_type"],
            "units": units, "invested": round(cost, 2) if cost is not None else None,
            "current_value": round(value, 2) if value is not None else None,
            "gain": round(value - cost, 2) if cost is not None and value is not None else None,
            "absolute_return_pct": _pct((value - cost) / cost) if cost and value is not None else None,
            "xirr_pct": _pct(rate), "lots": len(hl),
        })

    return {
        "holdings": out,
        "portfolio": {
            "invested": round(total_cost, 2), "current_value": round(total_value, 2),
            "gain": round(total_value - total_cost, 2),
            "absolute_return_pct": _pct((total_value - total_cost) / total_cost) if total_cost else None,
            "xirr_pct": _pct(xirr(portfolio_flows)) if portfolio_flows else None,
        },
    }


# ── Home loan: EMI schedule and tax benefit ───────────────────────────────────

@router.get("/loan-tracker/{loan_id}")
async def loan_tracker(loan_id: str, user_id: str = Depends(get_current_user)):
    rows = (
        get_supabase_client().table("loans").select("*").eq("id", loan_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    loan = rows[0]

    missing = [
        label for label, key in [("interest rate", "interest_rate"), ("tenure (months)", "tenure_months"), ("start date", "start_date")]
        if not loan.get(key)
    ]
    if not loan.get("principal_amount") and not loan.get("emi_amount"):
        missing.append("original loan amount or EMI")
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add to this loan: " + ", ".join(missing))

    try:
        schedule = build_schedule(
            principal=float(loan["principal_amount"]) if loan.get("principal_amount") else None,
            annual_pct=float(loan["interest_rate"]),
            emi=float(loan["emi_amount"]) if loan.get("emi_amount") else None,
            tenure_months=int(loan["tenure_months"]),
            start_date=date.fromisoformat(loan["start_date"]),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    today = date.today()
    summary = summarize(schedule, today)
    return {
        "loan": {k: loan.get(k) for k in ("id", "loan_type", "lender_name", "outstanding_amount", "emi_amount", "interest_rate", "tenure_months", "start_date", "principal_amount")},
        "summary": summary,
        "tax_applicable": loan["loan_type"] == "HOME_LOAN",
        "schedule": [
            {"number": i.number, "due_date": i.due_date.isoformat(), "opening": i.opening, "interest": i.interest,
             "principal": i.principal, "emi": round(i.emi, 2), "closing": i.closing, "paid": i.due_date <= today}
            for i in schedule
        ],
    }
