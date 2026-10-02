from __future__ import annotations

import base64
import json
import os

from anthropic import AsyncAnthropic

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


def content_block(data: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(data).decode()
    if media_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if media_type in ("image/jpeg", "image/png", "image/webp"):
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    return {"type": "text", "text": data.decode("utf-8", errors="replace")}


def parse_json(text: str):
    """Strip optional markdown code fences, then parse JSON."""
    s = text.strip()
    if "```" in s:
        for part in s.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith(("{", "[")):
                s = part
                break
    return json.loads(s)


TRANSACTIONS_PROMPT = (
    "Extract EVERY transaction from this Indian bank statement. Return ONLY a JSON array (no markdown, "
    "no explanation), one object per transaction, in statement order:\n"
    '[{"date":"YYYY-MM-DD","description":"<narration>","amount":<number>}]\n'
    "amount is a plain INR number: NEGATIVE for debits/withdrawals, POSITIVE for credits/deposits. "
    "Skip opening/closing balance rows and running-total rows."
)


async def extract_transactions(data: bytes, media_type: str) -> list[dict]:
    async with get_client().messages.stream(
        model=MODEL,
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": [content_block(data, media_type), {"type": "text", "text": TRANSACTIONS_PROMPT}],
        }],
    ) as stream:
        final = await stream.get_final_message()
    raw = next((b.text for b in final.content if getattr(b, "type", None) == "text"), "")
    result = parse_json(raw)
    if not isinstance(result, list):
        raise ValueError("Expected a JSON array of transactions")
    return result
