from __future__ import annotations

import json
import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from core.auth import get_current_user
from schemas.documents import UploadResponse
from services import ai
from services.ai import AIKeyError, Credentials, generate, parse_json
from services.credentials import key_rejected_error, resolve_credentials
from services.pdf import unlock_pdf

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_MEDIA_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/csv",
    "text/plain",
}

EXTRACTION_PROMPTS: dict[str, str] = {
    "payslip": (
        "Extract all payslip information and return ONLY a valid JSON object (no markdown, no explanation):\n"
        '{"doc_type":"payslip","month":"<Month Year e.g. March 2024 or null>","employer":"<company or null>",'
        '"employee_name":"<name or null>","gross_salary":<number or null>,"basic":<number or null>,'
        '"hra":<number or null>,"pf_employee":<number or null>,"pf_employer":<number or null>,'
        '"professional_tax":<number or null>,"tds":<number or null>,"net_salary":<number or null>,'
        '"total_deductions":<number or null>}\n'
        "All monetary values in INR as plain numbers (no currency symbols). Use null for missing fields."
    ),
    "bank_statement": (
        "Extract bank statement information and return ONLY a valid JSON object (no markdown, no explanation):\n"
        '{"doc_type":"bank_statement","bank_name":"<name or null>","account_number":"<last 4 digits or null>",'
        '"period_start":"<YYYY-MM-DD or null>","period_end":"<YYYY-MM-DD or null>",'
        '"opening_balance":<number or null>,"closing_balance":<number or null>,'
        '"total_credits":<number or null>,"total_debits":<number or null>,"transaction_count":<integer or null>}\n'
        "All monetary values in INR as plain numbers. Use null for missing fields."
    ),
    "form16": (
        "Extract Form 16 / TDS certificate information and return ONLY a valid JSON object (no markdown, no explanation):\n"
        '{"doc_type":"form16","financial_year":"<e.g. 2023-24 or null>","employer":"<company or null>",'
        '"employee_name":"<name or null>","pan":"<PAN or null>","gross_salary":<number or null>,'
        '"exempt_allowances":<number or null>,"net_taxable_salary":<number or null>,'
        '"total_income":<number or null>,"total_deductions_80c":<number or null>,'
        '"taxable_income":<number or null>,"tax_payable":<number or null>,"tds_deducted":<number or null>}\n'
        "All monetary values in INR as plain numbers. Use null for missing fields."
    ),
    "cas_statement": (
        "Extract Consolidated Account Statement (CAS) mutual fund portfolio information and return ONLY a valid JSON object (no markdown, no explanation):\n"
        '{"doc_type":"cas_statement","period_start":"<YYYY-MM-DD or null>","period_end":"<YYYY-MM-DD or null>",'
        '"investor_name":"<name or null>","pan":"<PAN or null>","total_portfolio_value":<number or null>,'
        '"total_invested":<total cost amount or null>,"total_gains":<unrealised gains or null>,'
        '"folio_count":<integer or null>,"scheme_count":<integer or null>}\n'
        "All monetary values in INR as plain numbers. Use null for missing fields."
    ),
}

def _auto_prompt() -> str:
    """One request that both identifies the document and extracts it, instead of a detect call followed by an
    extract call. Halves AI usage per upload (and per free-tier quota)."""
    parts = "\n\n".join(f"### If it is a {t}:\n{p}" for t, p in EXTRACTION_PROMPTS.items())
    return (
        "First identify this Indian financial document as one of: " + ", ".join(EXTRACTION_PROMPTS) + ". "
        "Then follow ONLY the matching instructions below and return ONLY that JSON object, whose doc_type field "
        'names the type. If it is none of these, return {"doc_type":"unknown"}.\n\n' + parts
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="auto"),
    password: str | None = Form(default=None),
    creds: Credentials = Depends(resolve_credentials),
    user_id: str = Depends(get_current_user),
) -> UploadResponse:
    media_type = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "").lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"

    if media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Allowed: PDF, JPEG, PNG, WebP, CSV.",
        )

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")

    if media_type == "application/pdf":
        content = unlock_pdf(content, password)
    resolved = doc_type if doc_type in EXTRACTION_PROMPTS else "auto"

    try:
        if resolved == "auto":
            raw = await generate(content, media_type, _auto_prompt(), creds=creds, max_tokens=8192)
            try:
                guess = parse_json(raw)
            except (json.JSONDecodeError, ValueError):
                return UploadResponse(doc_type="unknown", data={}, raw_extraction=raw, confidence="low")
            resolved = str(guess.get("doc_type", "unknown")).lower() if isinstance(guess, dict) else "unknown"
            if resolved not in EXTRACTION_PROMPTS:
                return UploadResponse(doc_type="unknown", data={}, confidence="low")
        else:
            raw = await generate(content, media_type, EXTRACTION_PROMPTS[resolved], creds=creds, max_tokens=8192)
    except AIKeyError as exc:
        raise key_rejected_error(exc)

    try:
        data = parse_json(raw)
    except (json.JSONDecodeError, ValueError):
        return UploadResponse(doc_type=resolved, data={}, raw_extraction=raw, confidence="low")

    return UploadResponse(doc_type=resolved, data=data, confidence="high")
