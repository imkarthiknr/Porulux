from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Free-tier quotas are counted per model, so a second model keeps extraction working when the first is spent.
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
logger = logging.getLogger(__name__)
PROVIDERS = ("gemini", "anthropic")
PROVIDER_LABELS = {"gemini": "Gemini", "anthropic": "Claude"}


@dataclass(frozen=True)
class Credentials:
    provider: str  # "gemini" | "anthropic"
    api_key: str
    shared: bool = False  # True when this is the app owner's key (grandfathered users)


class AIKeyError(Exception):
    """The provider rejected the API key (invalid or revoked; running out of quota is NOT this)."""

    def __init__(self, provider: str):
        super().__init__(provider)
        self.provider = provider


class AIQuotaError(Exception):
    """The provider is rate-limiting or the key's quota is used up. Retrying later (or another key) fixes it."""

    def __init__(self, provider: str, shared: bool, retry_seconds: int | None):
        super().__init__(provider)
        self.provider, self.shared, self.retry_seconds = provider, shared, retry_seconds


def _is_quota_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    return code == 429 or type(exc).__name__ == "RateLimitError" or "RESOURCE_EXHAUSTED" in text


def _retry_seconds(exc: Exception) -> int | None:
    text = str(exc)
    m = re.search(r"retryDelay'?\"?: ?'?\"?(\d+)s", text) or re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", text)
    if not m:
        return None
    if m.re.pattern.startswith("retryDelay"):
        return int(m.group(1))
    h, mnt, sec = m.groups()
    return int(h or 0) * 3600 + int(mnt or 0) * 60 + int(float(sec))


def _is_auth_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (401, 403):
        return True
    msg = str(exc).lower()
    return "api key not valid" in msg or "api_key_invalid" in msg or "invalid x-api-key" in msg


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini_part(data: bytes, media_type: str) -> types.Part:
    if media_type in ("text/csv", "text/plain"):
        return types.Part.from_text(text=data.decode("utf-8", errors="replace"))
    return types.Part.from_bytes(data=data, mime_type=media_type)


async def _gemini(
    creds: Credentials, data: bytes, media_type: str, prompt: str, max_tokens: int, json_output: bool, model: str | None = None,
) -> str:
    model = model or GEMINI_MODEL
    client = genai.Client(api_key=creds.api_key, http_options=types.HttpOptions(timeout=240_000))
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0,
        response_mime_type="application/json" if json_output else "text/plain",
        # Extraction doesn't need reasoning; 2.5-flash "thinks" by default, which is slow and costly.
        thinking_config=types.ThinkingConfig(thinking_budget=0) if "flash" in model else None,
    )
    res = await client.aio.models.generate_content(
        model=model, contents=[_gemini_part(data, media_type), prompt], config=config
    )
    return res.text or ""


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _anthropic_block(data: bytes, media_type: str) -> dict:
    if media_type == "application/pdf":
        b64 = base64.standard_b64encode(data).decode()
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if media_type in ("image/jpeg", "image/png", "image/webp"):
        b64 = base64.standard_b64encode(data).decode()
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    return {"type": "text", "text": data.decode("utf-8", errors="replace")}


async def _anthropic(creds: Credentials, data: bytes, media_type: str, prompt: str, max_tokens: int) -> str:
    client = AsyncAnthropic(api_key=creds.api_key, timeout=240.0)
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=min(max_tokens, 32000),
        messages=[{"role": "user", "content": [_anthropic_block(data, media_type), {"type": "text", "text": prompt}]}],
    ) as stream:
        final = await stream.get_final_message()
    return next((b.text for b in final.content if getattr(b, "type", None) == "text"), "")


# ── Public API ────────────────────────────────────────────────────────────────

async def generate(
    data: bytes, media_type: str, prompt: str, *, creds: Credentials, max_tokens: int, json_output: bool = True
) -> str:
    """Send a document plus an instruction to the user's chosen provider; return the text."""
    try:
        if creds.provider == "anthropic":
            return await _anthropic(creds, data, media_type, prompt, max_tokens)
        try:
            return await _gemini(creds, data, media_type, prompt, max_tokens, json_output)
        except Exception as exc:
            if not (_is_quota_error(exc) and GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL):
                raise
            logger.warning("Gemini quota hit on %s; retrying on %s", GEMINI_MODEL, GEMINI_FALLBACK_MODEL)
            return await _gemini(creds, data, media_type, prompt, max_tokens, json_output, model=GEMINI_FALLBACK_MODEL)
    except Exception as exc:
        if _is_auth_error(exc):
            raise AIKeyError(creds.provider) from exc
        if _is_quota_error(exc):
            raise AIQuotaError(creds.provider, creds.shared, _retry_seconds(exc)) from exc
        raise


async def validate_key(provider: str, api_key: str) -> None:
    """Cheap live check so users find out about a typo when saving, not mid-upload.
    Raises AIKeyError if the key is rejected; other failures (network, quota) propagate."""
    await generate(
        b"ping", "text/plain", "Reply with the single word OK.",
        creds=Credentials(provider, api_key), max_tokens=16, json_output=False,
    )


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


async def extract_transactions(data: bytes, media_type: str, *, creds: Credentials) -> tuple[float | None, list[dict]]:
    raw = await generate(data, media_type, TRANSACTIONS_PROMPT, creds=creds, max_tokens=32000)
    result = parse_json(raw)
    if isinstance(result, list):  # tolerate a bare array
        return None, result
    if not isinstance(result, dict) or not isinstance(result.get("transactions"), list):
        raise ValueError("Expected an object with a transactions array")
    opening = result.get("opening_balance")
    return (float(opening) if isinstance(opening, (int, float)) else None), result["transactions"]
