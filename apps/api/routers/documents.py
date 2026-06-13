from __future__ import annotations

import base64
import json
import mimetypes

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from core.auth import get_current_user
from schemas.documents import UploadResponse

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

_client = AsyncAnthropic()

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

AUTO_DETECT_PROMPT = (
    "Identify this Indian financial document type. "
    "Reply with EXACTLY one of these words and nothing else: "
    "payslip, bank_statement, form16, cas_statement, unknown"
)


def _content_block(data: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(data).decode()
    if media_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if media_type in ("image/jpeg", "image/png", "image/webp"):
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    # CSV / plain text
    return {"type": "text", "text": data.decode("utf-8", errors="replace")}


def _parse_json(text: str) -> dict:
    """Strip optional markdown code fences, then parse JSON."""
    s = text.strip()
    if "```" in s:
        for part in s.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                s = part
                break
    return json.loads(s)


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="auto"),
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

    block = _content_block(content, media_type)
    resolved = doc_type if doc_type in EXTRACTION_PROMPTS else "auto"

    # Step 1: Auto-detect document type when not specified
    if resolved == "auto":
        detect = await _client.messages.create(
            model="claude-opus-4-8",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": [block, {"type": "text", "text": AUTO_DETECT_PROMPT}],
            }],
        )
        resolved = detect.content[0].text.strip().lower()
        if resolved not in EXTRACTION_PROMPTS:
            return UploadResponse(doc_type="unknown", data={}, confidence="low")

    # Step 2: Extract structured data with streaming (documents can be large)
    prompt = EXTRACTION_PROMPTS[resolved]
    async with _client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{
            "role": "user",
            "content": [block, {"type": "text", "text": prompt}],
        }],
    ) as stream:
        final = await stream.get_final_message()

    raw = next(
        (b.text for b in final.content if getattr(b, "type", None) == "text"),
        "",
    )

    try:
        data = _parse_json(raw)
    except (json.JSONDecodeError, ValueError):
        return UploadResponse(doc_type=resolved, data={}, raw_extraction=raw, confidence="low")

    return UploadResponse(doc_type=resolved, data=data, confidence="high")
