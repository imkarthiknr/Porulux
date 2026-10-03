from __future__ import annotations

import logging
import mimetypes
from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from core.auth import AuthUser, get_auth_user, get_current_user
from core.crud import make_crud_router
from core.supabase import get_supabase_client
from schemas.banking import CreditCard, CreditCardCreate, CreditCardUpdate
from services.ai import AIKeyError, AIQuotaError
from services.bank_import import ImportError_
from services.card_import import ParsedStatement, extract_card_statement, parse_card_csv
from services.cards import card_overview, upcoming_dues
from services.categorizer import categorize
from services.credentials import key_rejected_error, resolve_credentials
from services.pdf import unlock_pdf

logger = logging.getLogger(__name__)

cards_crud = make_crud_router(
    prefix="/api/v1/credit-cards", tag="credit-cards", table="credit_cards",
    create_schema=CreditCardCreate, update_schema=CreditCardUpdate, read_schema=CreditCard,
)

router = APIRouter(prefix="/api/v1/credit-cards", tags=["credit-cards"])

PAYMENT_CATEGORY = "Payment/Refund"
_MAX_UPLOAD = 20 * 1024 * 1024
_AI_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def own_card(user_id: str, card_id: str) -> dict:
    rows = (
        get_supabase_client().table("credit_cards").select("*")
        .eq("id", card_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Card not found")
    return rows[0]


def own_statement(user_id: str, statement_id: str) -> dict:
    rows = (
        get_supabase_client().table("card_statements").select("*")
        .eq("id", statement_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Statement not found")
    return rows[0]


@router.get("/overview")
async def overview(user_id: str = Depends(get_current_user)):
    client = get_supabase_client()
    cards = client.table("credit_cards").select("*").eq("user_id", user_id).execute().data
    statements = client.table("card_statements").select("*").eq("user_id", user_id).execute().data
    by_card: dict[str, list[dict]] = defaultdict(list)
    for s in statements:
        by_card[s["card_id"]].append(s)

    today = date.today()
    items = [card_overview(c, by_card.get(c["id"], []), today) for c in sorted(cards, key=lambda c: (c["bank_name"], c["last4"]))]
    limit = sum(i["credit_limit"] or 0 for i in items)
    owed = sum(i["outstanding"] for i in items)
    return {
        "cards": items,
        "totals": {
            "credit_limit": round(limit, 2),
            "outstanding": round(owed, 2),
            "utilization_pct": round(owed / limit * 100, 1) if limit else None,
        },
        "upcoming_dues": upcoming_dues(items),
    }


@router.get("/{card_id}/statements")
async def list_statements(card_id: str, user_id: str = Depends(get_current_user)):
    own_card(user_id, card_id)
    return (
        get_supabase_client().table("card_statements").select("*")
        .eq("card_id", card_id).eq("user_id", user_id).order("statement_date", desc=True).execute()
    ).data


@router.get("/statements/{statement_id}/transactions")
async def statement_transactions(statement_id: str, user_id: str = Depends(get_current_user)):
    stmt = own_statement(user_id, statement_id)
    txns = (
        get_supabase_client().table("card_transactions").select("*")
        .eq("statement_id", statement_id).eq("user_id", user_id).order("txn_date", desc=False).execute()
    ).data
    spend: dict[str, float] = defaultdict(float)
    for t in txns:
        if float(t["amount"]) > 0:
            spend[t.get("category") or "Other"] += float(t["amount"])
    return {
        "statement": stmt,
        "transactions": txns,
        "by_category": [{"category": c, "total": round(v, 2)} for c, v in sorted(spend.items(), key=lambda kv: -kv[1])],
    }


class StatementUpdate(BaseModel):
    paid: Optional[bool] = None
    due_date: Optional[date] = None
    total_due: Optional[float] = Field(None, ge=0)
    minimum_due: Optional[float] = Field(None, ge=0)


@router.patch("/statements/{statement_id}")
async def update_statement(statement_id: str, payload: StatementUpdate, user_id: str = Depends(get_current_user)):
    own_statement(user_id, statement_id)
    data = payload.model_dump(exclude_unset=True, mode="json")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    return (
        get_supabase_client().table("card_statements").update(data)
        .eq("id", statement_id).eq("user_id", user_id).execute()
    ).data[0]


@router.delete("/statements/{statement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_statement(statement_id: str, user_id: str = Depends(get_current_user)):
    own_statement(user_id, statement_id)
    get_supabase_client().table("card_statements").delete().eq("id", statement_id).eq("user_id", user_id).execute()


@router.post("/{card_id}/statements/import", status_code=status.HTTP_201_CREATED)
async def import_card_statement(
    card_id: str,
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    user: AuthUser = Depends(get_auth_user),
):
    """PDF/image statements are read by the user's AI key; CSV needs no key."""
    card = own_card(user.id, card_id)
    media_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    is_csv = media_type in ("text/csv", "application/vnd.ms-excel", "text/plain") or (file.filename or "").lower().endswith(".csv")

    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB limit.")

    parsed: ParsedStatement
    if is_csv:
        try:
            parsed = parse_card_csv(content)
        except ImportError_ as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    elif media_type in _AI_TYPES:
        if media_type == "application/pdf":
            content = unlock_pdf(content, password)
        creds = await resolve_credentials(user)
        try:
            parsed = await extract_card_statement(content, media_type, creds=creds)
        except AIKeyError as exc:
            raise key_rejected_error(exc)
        except AIQuotaError:
            raise   # handled app-wide as a clear 429, not a vague 502
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not find the statement date and total due in this document. Is it a credit card statement?",
            )
        except Exception:
            logger.exception("Card statement extraction failed (%s, %d bytes)", media_type, len(content))
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="The AI could not read this statement. Try a CSV export, or try again.")
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, image or CSV statement.")

    if parsed.card_last4 and parsed.card_last4 != card["last4"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This statement is for a card ending {parsed.card_last4}, but you picked the card ending {card['last4']}.",
        )

    client = get_supabase_client()
    dup = (
        client.table("card_statements").select("id").eq("card_id", card_id)
        .eq("statement_date", parsed.statement_date.isoformat()).limit(1).execute()
    ).data
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"The statement dated {parsed.statement_date.isoformat()} is already imported for this card.")

    stmt = client.table("card_statements").insert({
        "user_id": user.id, "card_id": card_id,
        "statement_date": parsed.statement_date.isoformat(),
        "period_start": parsed.period_start.isoformat() if parsed.period_start else None,
        "period_end": parsed.period_end.isoformat() if parsed.period_end else None,
        "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
        "total_due": parsed.total_due, "minimum_due": parsed.minimum_due, "credit_limit": parsed.credit_limit,
        "paid": parsed.total_due <= 0, "source": parsed.source,
    }).execute().data[0]

    # Same transaction can legitimately repeat (two identical coffees), so count occurrences.
    seen: dict[tuple, int] = defaultdict(int)
    if parsed.transactions:
        lo = min(t.txn_date for t in parsed.transactions).isoformat()
        hi = max(t.txn_date for t in parsed.transactions).isoformat()
        for r in (
            client.table("card_transactions").select("txn_date,description,amount")
            .eq("card_id", card_id).gte("txn_date", lo).lte("txn_date", hi).limit(10000).execute()
        ).data:
            seen[(r["txn_date"], r["description"], round(float(r["amount"]), 2))] += 1

    rows, skipped = [], 0
    for t in parsed.transactions:
        key = (t.txn_date.isoformat(), t.description, t.amount)
        if seen[key] > 0:
            seen[key] -= 1
            skipped += 1
            continue
        rows.append({
            "user_id": user.id, "card_id": card_id, "statement_id": stmt["id"],
            "txn_date": t.txn_date.isoformat(), "description": t.description, "amount": t.amount,
            # categorize() reads a debit as negative, and for a card a purchase is positive
            "category": PAYMENT_CATEGORY if t.amount < 0 else categorize(t.description, -t.amount),
        })
    for i in range(0, len(rows), 500):
        client.table("card_transactions").insert(rows[i:i + 500]).execute()

    return {"statement": stmt, "transactions_inserted": len(rows), "duplicates_skipped": skipped}
