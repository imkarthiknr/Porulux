from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _part(data: bytes, media_type: str) -> types.Part:
    if media_type in ("text/csv", "text/plain"):
        return types.Part.from_text(text=data.decode("utf-8", errors="replace"))
    return types.Part.from_bytes(data=data, mime_type=media_type)


async def generate(data: bytes, media_type: str, prompt: str, *, max_tokens: int, json_output: bool = True) -> str:
    """Send a document plus an instruction to Gemini and return the text response."""
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0,
        response_mime_type="application/json" if json_output else "text/plain",
    )
    res = await get_client().aio.models.generate_content(
        model=MODEL, contents=[_part(data, media_type), prompt], config=config
    )
    return res.text or ""


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
    raw = await generate(data, media_type, TRANSACTIONS_PROMPT, max_tokens=32000)
    result = parse_json(raw)
    if not isinstance(result, list):
        raise ValueError("Expected a JSON array of transactions")
    return result
