from __future__ import annotations

import mimetypes
from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from postgrest.exceptions import APIError

from core.auth import get_current_user
from core.supabase import get_supabase_client
from schemas.transactions import (
    CategoryTotal,
    ImportResult,
    MonthlySummary,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
)
from services import ai
from services.bank_import import ImportError_, ParsedTransaction, parse_csv, parse_date
from services.categorizer import CATEGORIES, categorize

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])

_TABLE = "bank_transactions"
_MAX_UPLOAD = 20 * 1024 * 1024
_AI_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def _month_bounds(month: str) -> tuple[str, str]:
    try:
        y, m = (int(p) for p in month.split("-"))
        start = date(y, m, 1)
        end = date(y + (m == 12), m % 12 + 1, 1)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="month must be YYYY-MM")
    return start.isoformat(), end.isoformat()


@router.get("/categories", response_model=list[str])
async def list_categories():
    return CATEGORIES


@router.get("", response_model=list[Transaction])
async def list_transactions(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    category: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    user_id: str = Depends(get_current_user),
):
    q = get_supabase_client().table(_TABLE).select("*").eq("user_id", user_id)
    if month:
        start, end = _month_bounds(month)
        q = q.gte("transaction_date", start).lt("transaction_date", end)
    if category:
        q = q.eq("category", category)
    return q.order("transaction_date", desc=True).order("created_at", desc=True).limit(limit).execute().data


@router.post("", response_model=Transaction, status_code=status.HTTP_201_CREATED)
async def create_transaction(payload: TransactionCreate, user_id: str = Depends(get_current_user)):
    data = payload.model_dump(exclude_none=True, mode="json")
    data["user_id"] = user_id
    data.setdefault("category", categorize(payload.description, payload.amount))
    try:
        res = get_supabase_client().table(_TABLE).insert(data).execute()
    except APIError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return res.data[0]


@router.patch("/{txn_id}", response_model=Transaction)
async def update_transaction(
    txn_id: str, payload: TransactionUpdate, user_id: str = Depends(get_current_user)
):
    data = payload.model_dump(exclude_unset=True, mode="json")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    try:
        res = (
            get_supabase_client().table(_TABLE).update(data)
            .eq("id", txn_id).eq("user_id", user_id).execute()
        )
    except APIError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return res.data[0]


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(txn_id: str, user_id: str = Depends(get_current_user)):
    res = get_supabase_client().table(_TABLE).delete().eq("id", txn_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")


@router.get("/summary", response_model=MonthlySummary)
async def monthly_summary(
    month: str = Query(..., description="YYYY-MM"),
    user_id: str = Depends(get_current_user),
):
    start, end = _month_bounds(month)
    rows = (
        get_supabase_client().table(_TABLE).select("amount,category")
        .eq("user_id", user_id).gte("transaction_date", start).lt("transaction_date", end)
        .limit(10000).execute()
    ).data
    income = sum(r["amount"] for r in rows if r["amount"] > 0)
    expenses = sum(-r["amount"] for r in rows if r["amount"] < 0)
    by_cat: dict[str, float] = defaultdict(float)
    for r in rows:
        if r["amount"] < 0:
            by_cat[r["category"] or "Other"] += -r["amount"]
    return MonthlySummary(
        month=month,
        income=round(income, 2),
        expenses=round(expenses, 2),
        net=round(income - expenses, 2),
        by_category=[
            CategoryTotal(category=c, total=round(t, 2))
            for c, t in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
    )


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_statement(
    file: UploadFile = File(...),
    bank_name: Optional[str] = Form(None),
    account_last4: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user),
):
    """Import a bank statement (CSV parsed locally; PDF/image extracted with Gemini),
    auto-categorise, and skip rows already imported."""
    media_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    name = (file.filename or "").lower()
    is_csv = media_type in ("text/csv", "application/vnd.ms-excel", "text/plain") or name.endswith(".csv")

    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB limit.")

    parsed: list[ParsedTransaction] = []
    if is_csv:
        try:
            parsed = parse_csv(content)
        except ImportError_ as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    elif media_type in _AI_TYPES:
        try:
            for item in await ai.extract_transactions(content, media_type):
                d = parse_date(str(item.get("date", "")))
                amount = item.get("amount")
                desc = str(item.get("description") or "").strip()
                if d and desc and isinstance(amount, (int, float)) and amount != 0:
                    parsed.append(ParsedTransaction(d, desc, round(float(amount), 2)))
        except Exception:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Could not extract transactions from this document.")
        if not parsed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No transactions found in the document.")
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a CSV, PDF, JPEG, PNG or WebP statement.")

    client = get_supabase_client()
    lo = min(t.transaction_date for t in parsed).isoformat()
    hi = max(t.transaction_date for t in parsed).isoformat()
    existing = (
        client.table(_TABLE).select("transaction_date,description,amount")
        .eq("user_id", user_id).gte("transaction_date", lo).lte("transaction_date", hi)
        .limit(10000).execute()
    ).data
    # Identical rows within one file are legitimate (two same-day coffees), so count
    # occurrences instead of using a set.
    seen: dict[tuple, int] = defaultdict(int)
    for r in existing:
        seen[(r["transaction_date"], r["description"], round(float(r["amount"]), 2))] += 1

    rows, skipped = [], 0
    for t in parsed:
        key = (t.transaction_date.isoformat(), t.description, t.amount)
        if seen[key] > 0:
            seen[key] -= 1
            skipped += 1
            continue
        rows.append({
            "user_id": user_id,
            "transaction_date": t.transaction_date.isoformat(),
            "description": t.description,
            "amount": t.amount,
            "category": categorize(t.description, t.amount),
            "bank_name": bank_name,
            "account_last4": account_last4,
        })
    for i in range(0, len(rows), 500):
        client.table(_TABLE).insert(rows[i:i + 500]).execute()

    return ImportResult(parsed=len(parsed), inserted=len(rows), duplicates_skipped=skipped)
