from __future__ import annotations

import logging
import mimetypes
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from core.auth import AuthUser, get_auth_user, get_current_user
from core.supabase import get_supabase_client
from services.ai import AIKeyError, AIQuotaError
from services.bank_import import ImportError_
from services.credentials import key_rejected_error, resolve_credentials
from services.loan_statements import ParsedLoanStatement, extract_loan_statement, parse_loan_csv, summarize_account
from services.pdf import unlock_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/loans", tags=["loan-statements"])

_MAX_UPLOAD = 20 * 1024 * 1024
_AI_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def own_loan(user_id: str, loan_id: str) -> dict:
    rows = (
        get_supabase_client().table("loans").select("*")
        .eq("id", loan_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Loan not found")
    return rows[0]


def _load(user_id: str, loan_id: str) -> tuple[list[dict], list[dict]]:
    client = get_supabase_client()
    txns = client.table("loan_transactions").select("*").eq("loan_id", loan_id).eq("user_id", user_id).limit(20000).execute().data
    stmts = client.table("loan_statements").select("*").eq("loan_id", loan_id).eq("user_id", user_id).execute().data
    return txns, stmts


@router.get("/{loan_id}/account")
async def loan_account(loan_id: str, user_id: str = Depends(get_current_user)):
    """Everything imported for this loan: totals so far, the statements, and the transactions (newest first)."""
    loan = own_loan(user_id, loan_id)
    txns, stmts = _load(user_id, loan_id)
    return {
        "summary": summarize_account(txns, stmts, loan),
        "statements": sorted(stmts, key=lambda s: s["statement_date"], reverse=True),
        "transactions": sorted(txns, key=lambda t: (t["txn_date"], t.get("line_no") or 0), reverse=True),
    }


@router.delete("/statements/{statement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan_statement(statement_id: str, user_id: str = Depends(get_current_user)):
    client = get_supabase_client()
    rows = client.table("loan_statements").select("id").eq("id", statement_id).eq("user_id", user_id).limit(1).execute().data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Statement not found")
    # loan_transactions.statement_id cascades, so its transactions go with it
    client.table("loan_statements").delete().eq("id", statement_id).eq("user_id", user_id).execute()


@router.post("/{loan_id}/statements/import", status_code=status.HTTP_201_CREATED)
async def import_loan_statement(
    loan_id: str,
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    user: AuthUser = Depends(get_auth_user),
):
    """PDF/image statements are read by the user's AI key; CSV needs no key."""
    own_loan(user.id, loan_id)
    media_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    is_csv = media_type in ("text/csv", "application/vnd.ms-excel", "text/plain") or (file.filename or "").lower().endswith(".csv")

    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB limit.")

    parsed: ParsedLoanStatement
    if is_csv:
        try:
            parsed = parse_loan_csv(content)
        except ImportError_ as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    elif media_type in _AI_TYPES:
        if media_type == "application/pdf":
            content = unlock_pdf(content, password)
        creds = await resolve_credentials(user)
        try:
            parsed = await extract_loan_statement(content, media_type, creds=creds)
        except AIKeyError as exc:
            raise key_rejected_error(exc)
        except AIQuotaError:
            raise   # handled app-wide as a clear 429
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not find any transactions in this document. Is it a loan account statement?",
            )
        except Exception:
            logger.exception("Loan statement extraction failed (%s, %d bytes)", media_type, len(content))
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="The AI could not read this statement. Try a CSV export, or try again.")
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, image or CSV statement.")

    client = get_supabase_client()
    # Same period as one already imported is a re-upload. (A statement's printed date is not used: PDFs
    # downloaded together share it even when they cover different years.)
    for existing in client.table("loan_statements").select("period_start,period_end").eq("loan_id", loan_id).execute().data:
        if existing.get("period_start") == parsed.period_start.isoformat() and existing.get("period_end") == parsed.period_end.isoformat():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"A statement covering {parsed.period_start.isoformat()} to {parsed.period_end.isoformat()} is already imported for this loan.",
            )

    # Statements often overlap (a yearly one after a half-yearly one), so skip lines already stored.
    # The same line can legitimately repeat, so count occurrences rather than just checking presence.
    lo = min(t.txn_date for t in parsed.transactions).isoformat()
    hi = max(t.txn_date for t in parsed.transactions).isoformat()
    seen: dict[tuple, int] = defaultdict(int)
    for r in (
        client.table("loan_transactions").select("txn_date,description,kind,amount")
        .eq("loan_id", loan_id).gte("txn_date", lo).lte("txn_date", hi).limit(20000).execute()
    ).data:
        seen[(r["txn_date"], r["description"], r["kind"], round(float(r["amount"]), 2))] += 1

    fresh, skipped = [], 0
    for n, t in enumerate(parsed.transactions):
        key = (t.txn_date.isoformat(), t.description, t.kind, t.amount)
        if seen[key] > 0:
            seen[key] -= 1
            skipped += 1
        else:
            fresh.append((n, t))
    if not fresh:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Every transaction in this statement is already imported for this loan.")

    stmt = client.table("loan_statements").insert({
        "user_id": user.id, "loan_id": loan_id,
        "statement_date": parsed.statement_date.isoformat(),
        "period_start": parsed.period_start.isoformat(),
        "period_end": parsed.period_end.isoformat(),
        "opening_balance": parsed.opening_balance, "closing_balance": parsed.closing_balance,
        "source": parsed.source,
    }).execute().data[0]

    rows = [{
        "user_id": user.id, "loan_id": loan_id, "statement_id": stmt["id"], "line_no": n,
        "txn_date": t.txn_date.isoformat(), "description": t.description, "kind": t.kind, "amount": t.amount,
        "principal_amount": t.principal, "interest_amount": t.interest, "charges_amount": t.charges,
        "balance_after": t.balance,
    } for n, t in fresh]
    for i in range(0, len(rows), 500):
        client.table("loan_transactions").insert(rows[i:i + 500]).execute()

    return {"statement": stmt, "transactions_inserted": len(rows), "duplicates_skipped": skipped}
