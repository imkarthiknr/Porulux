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
        _client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=240_000),  # ms; fail instead of hanging forever
        )
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
        # Extraction doesn't need reasoning; 2.5-flash "thinks" by default, which is slow and costly.
        thinking_config=types.ThinkingConfig(thinking_budget=0) if "flash" in MODEL else None,
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
    "Extract EVERY transaction from this Indian bank statement. Return ONLY a JSON object (no markdown, "
    "no explanation):\n"
    '{"opening_balance":<number or null>,"transactions":[{"date":"YYYY-MM-DD","description":"<narration>","amount":<number>}]}\n'
    "opening_balance is the account balance before the first transaction (the statement's opening balance), "
    "or null if not shown. amount is a plain INR number: NEGATIVE for debits/withdrawals, POSITIVE for "
    "credits/deposits. List transactions in statement order. Skip opening/closing balance rows and running-total rows."
)


async def extract_transactions(data: bytes, media_type: str) -> tuple[float | None, list[dict]]:
    raw = await generate(data, media_type, TRANSACTIONS_PROMPT, max_tokens=32000)
    result = parse_json(raw)
    if isinstance(result, list):  # tolerate a bare array
        return None, result
    if not isinstance(result, dict) or not isinstance(result.get("transactions"), list):
        raise ValueError("Expected an object with a transactions array")
    opening = result.get("opening_balance")
    return (float(opening) if isinstance(opening, (int, float)) else None), result["transactions"]
