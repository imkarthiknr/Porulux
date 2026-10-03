from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from core.auth import AuthUser, get_auth_user
from core.supabase import get_supabase_client
from services.ai import AIKeyError
from services.credentials import key_rejected_error, resolve_credentials
from services.holdings_import import (
    ParseResult, extract_holdings, guess_source, parse_tabular, reconcile,
)
from services.pdf import unlock_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/investments/import", tags=["investments-import"])

_MAX_UPLOAD = 20 * 1024 * 1024
_MAX_ROWS = 1000
_AI_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def _existing(user_id: str) -> list[dict]:
    return (
        get_supabase_client().table("holdings")
        .select("id,symbol,name,isin,units,avg_buy_price,current_price,source")
        .eq("user_id", user_id).limit(5000).execute()
    ).data


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    source: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    user: AuthUser = Depends(get_auth_user),
):
    """Parse a holdings statement and show what importing it would do. Saves nothing.
    CSV/XLSX are parsed locally; PDFs and images are read with the caller's AI key."""
    filename = file.filename or ""
    low = filename.lower()
    media_type = (file.content_type or mimetypes.guess_type(filename)[0] or "").lower()
    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB limit.")

    is_sheet = low.endswith((".csv", ".xlsx", ".xlsm", ".tsv", ".txt")) or media_type in (
        "text/csv", "text/plain", "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    parsed: ParseResult
    if low.endswith(".xls") and not low.endswith(".xlsx"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Old .xls files are not supported. Re-save it as .xlsx or CSV.")
    if is_sheet:
        try:
            parsed = parse_tabular(content, filename)
        except Exception:
            logger.exception("Holdings sheet parse failed (%s)", filename)
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not read that file. Export your holdings as CSV or XLSX and try again.")
        if not parsed.holdings:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No holdings found. Look for a holdings export with columns like Instrument, Quantity and Average price, or upload the PDF statement instead.",
            )
    elif media_type in _AI_TYPES or low.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp")):
        if media_type == "application/pdf" or low.endswith(".pdf"):
            media_type = "application/pdf"
            content = unlock_pdf(content, password)
        creds = await resolve_credentials(user)
        try:
            parsed = await extract_holdings(content, media_type, creds=creds)
        except AIKeyError as exc:
            raise key_rejected_error(exc)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not find a list of holdings in this document.")
        except Exception:
            logger.exception("Holdings extraction failed (%s, %d bytes)", media_type, len(content))
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="The AI could not read this statement. Try a CSV/XLSX export, or try again.")
        if not parsed.holdings:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No holdings found in this document.")
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a CSV, XLSX, PDF or image statement.")

    if len(parsed.holdings) > _MAX_ROWS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"That statement has more than {_MAX_ROWS} holdings.")

    src = (source or "").strip() or parsed.source_hint or guess_source(filename) or "Imported"
    entries, missing = reconcile(parsed.holdings, _existing(user.id), src)
    counts = {a: sum(1 for e in entries if e["action"] == a) for a in ("new", "update", "unchanged")}
    return {
        "source": src[:60],
        "entries": entries,
        "missing": missing,
        "warnings": parsed.warnings[:20],
        "counts": counts,
        "totals": {
            "invested": round(sum(e["invested"] or 0 for e in entries), 2),
            "current_value": round(sum(e["current_value"] or 0 for e in entries), 2),
        },
    }


class ConfirmRow(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    symbol: str = Field(..., min_length=1, max_length=40)
    isin: Optional[str] = Field(None, pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    holding_type: Literal["STOCK", "MF", "ETF", "BOND", "SGB", "OTHER"]
    units: float = Field(..., gt=0)
    avg_buy_price: Optional[float] = Field(None, ge=0)
    current_price: Optional[float] = Field(None, ge=0)
    existing_id: Optional[UUID] = None


class ConfirmBody(BaseModel):
    source: str = Field(..., min_length=1, max_length=60)
    rows: list[ConfirmRow] = Field(..., max_length=_MAX_ROWS)
    remove_ids: list[UUID] = Field(default_factory=list, max_length=_MAX_ROWS)


@router.post("/confirm")
async def confirm(body: ConfirmBody, user: AuthUser = Depends(get_auth_user)):
    """Apply a previewed import: add new holdings, update matched ones, optionally remove the ones the
    statement no longer lists. Everything is checked against the caller's own holdings again here."""
    client = get_supabase_client()
    source = body.source.strip()
    mine = {str(r["id"]): r for r in _existing(user.id)}
    now = datetime.now(timezone.utc).isoformat()

    for row in body.rows:
        if row.existing_id and str(row.existing_id) not in mine:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="One of the holdings no longer exists. Preview the file again.")
    removable = [str(i) for i in body.remove_ids if str(i) in mine and mine[str(i)].get("source") == source]

    inserts, updated = [], 0
    for row in body.rows:
        fields = {
            "name": row.name.strip(), "symbol": row.symbol.strip(), "isin": row.isin, "holding_type": row.holding_type,
            "units": row.units, "avg_buy_price": row.avg_buy_price, "current_price": row.current_price,
            "source": source, "last_imported_at": now,
        }
        if row.existing_id:
            # Keep values the statement didn't carry (e.g. a price it omitted) instead of nulling them.
            patch = {k: v for k, v in fields.items() if v is not None}
            client.table("holdings").update(patch).eq("id", str(row.existing_id)).eq("user_id", user.id).execute()
            updated += 1
        else:
            inserts.append({**{k: v for k, v in fields.items() if v is not None}, "user_id": user.id})
    for i in range(0, len(inserts), 500):
        client.table("holdings").insert(inserts[i:i + 500]).execute()
    for hid in removable:
        client.table("holdings").delete().eq("id", hid).eq("user_id", user.id).execute()

    return {"inserted": len(inserts), "updated": updated, "removed": len(removable)}
