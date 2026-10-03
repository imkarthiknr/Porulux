import asyncio
import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import main
from core import crud
from core.auth import AuthUser, get_auth_user
from routers import documents, holdings_import
from services import ai, credentials
from services.ai import AIQuotaError, Credentials
from tests.fakedb import FakeDB

# The real message Gemini returned when the shared key's free tier ran out (trimmed).
REAL_429 = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota. "
    "Please retry in 12h4m50.577603875s.', 'status': 'RESOURCE_EXHAUSTED', 'details': "
    "[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '43490s'}]}}"
)


class FakeGeminiError(Exception):
    code = 429


def test_retry_seconds_parsed_from_both_shapes_of_the_real_message():
    assert ai._retry_seconds(FakeGeminiError(REAL_429)) == 43490
    assert ai._retry_seconds(FakeGeminiError("Please retry in 12h4m50.5s.")) == 12 * 3600 + 4 * 60 + 50
    assert ai._retry_seconds(FakeGeminiError("Please retry in 30.2s.")) == 30
    assert ai._retry_seconds(FakeGeminiError("something else")) is None


def test_quota_detection_covers_gemini_and_anthropic_shapes():
    class RateLimitError(Exception):
        pass

    assert ai._is_quota_error(FakeGeminiError("x")) and ai._is_quota_error(RateLimitError("x"))
    assert ai._is_quota_error(RuntimeError("RESOURCE_EXHAUSTED ..."))
    assert not ai._is_quota_error(RuntimeError("boom"))


def run_generate(creds):
    return asyncio.run(ai.generate(b"x", "text/plain", "p", creds=creds, max_tokens=10))


def test_gemini_quota_falls_back_to_the_second_model(monkeypatch):
    seen = []

    async def fake(creds, data, media_type, prompt, max_tokens, json_output, model=None):
        seen.append(model or ai.GEMINI_MODEL)
        if (model or ai.GEMINI_MODEL) == ai.GEMINI_MODEL:
            raise FakeGeminiError(REAL_429)
        return "from fallback"

    monkeypatch.setattr(ai, "_gemini", fake)
    assert run_generate(Credentials("gemini", "k", shared=True)) == "from fallback"
    assert seen == [ai.GEMINI_MODEL, ai.GEMINI_FALLBACK_MODEL]


def test_both_models_exhausted_raises_a_quota_error_with_the_wait(monkeypatch):
    async def fake(*a, **k):
        raise FakeGeminiError(REAL_429)

    monkeypatch.setattr(ai, "_gemini", fake)
    with pytest.raises(AIQuotaError) as e:
        run_generate(Credentials("gemini", "k", shared=True))
    assert e.value.shared and e.value.retry_seconds == 43490


def test_no_pointless_fallback_when_it_is_the_same_model(monkeypatch):
    calls = []

    async def fake(*a, **k):
        calls.append(1)
        raise FakeGeminiError(REAL_429)

    monkeypatch.setattr(ai, "_gemini", fake)
    monkeypatch.setattr(ai, "GEMINI_FALLBACK_MODEL", ai.GEMINI_MODEL)
    with pytest.raises(AIQuotaError):
        run_generate(Credentials("gemini", "k"))
    assert len(calls) == 1


def test_non_quota_errors_are_not_retried_or_disguised(monkeypatch):
    async def fake(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ai, "_gemini", fake)
    with pytest.raises(RuntimeError):
        run_generate(Credentials("gemini", "k"))


# ── what the user sees ────────────────────────────────────────────────────────

ME = "00000000-0000-0000-0000-00000000000a"
USER = AuthUser(ME, datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")


def pdf():
    w = PdfWriter(); w.add_blank_page(100, 100)
    b = io.BytesIO(); w.write(b)
    return b.getvalue()


def boot(monkeypatch, **tables):
    db = FakeDB(**tables)
    for mod in (crud, credentials, holdings_import):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    monkeypatch.setenv("SHARED_KEY_CUTOFF", "2026-10-03T00:00:00Z")
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    return TestClient(main.app, raise_server_exceptions=False), db


@pytest.fixture(autouse=True)
def _clean():
    yield
    main.app.dependency_overrides.clear()


@pytest.mark.parametrize("path,files", [
    ("/api/v1/documents/upload", {"file": ("a.pdf", pdf(), "application/pdf")}),
    ("/api/v1/investments/import/preview", {"file": ("cas.pdf", pdf(), "application/pdf")}),
])
def test_quota_is_a_clear_429_not_a_500_on_every_ai_endpoint(monkeypatch, path, files):
    c, _ = boot(monkeypatch)

    async def fake(*a, **k):
        raise FakeGeminiError(REAL_429)

    monkeypatch.setattr(ai, "_gemini", fake)
    res = c.post(path, files=files)
    assert res.status_code == 429
    detail = res.json()["detail"]
    assert detail.startswith("AI_QUOTA") and "shared Gemini allowance" in detail and "12h 4m" in detail and "Settings" in detail


def test_own_key_quota_message_points_at_billing_not_settings(monkeypatch):
    c, _ = boot(monkeypatch)
    monkeypatch.setattr(credentials, "stored_key_row", lambda uid: {"provider": "gemini", "encrypted_key": "x", "key_last4": "1234"})
    monkeypatch.setattr(credentials.keyvault, "decrypt", lambda t: "their-own-key")

    async def fake(*a, **k):
        raise FakeGeminiError("Please retry in 20s.")

    monkeypatch.setattr(ai, "_gemini", fake)
    res = c.post("/api/v1/documents/upload", files={"file": ("a.pdf", pdf(), "application/pdf")})
    assert res.status_code == 429 and "Your Gemini key" in res.json()["detail"] and "billing" in res.json()["detail"]


# ── one AI call per auto-detected upload ──────────────────────────────────────

def test_auto_detect_uses_a_single_request_and_returns_the_right_type(monkeypatch):
    c, _ = boot(monkeypatch)
    calls = []

    async def fake_generate(data, media_type, prompt, *, creds, **kw):
        calls.append(prompt)
        return '{"doc_type":"payslip","month":"May 2026","net_salary":136021,"gross_salary":191238}'

    monkeypatch.setattr(documents, "generate", fake_generate)
    res = c.post("/api/v1/documents/upload", files={"file": ("p.pdf", pdf(), "application/pdf")})
    body = res.json()
    assert res.status_code == 200 and body["doc_type"] == "payslip" and body["data"]["net_salary"] == 136021
    assert len(calls) == 1                                                       # was 2 (detect, then extract)
    assert all(t in calls[0] for t in ("payslip", "bank_statement", "form16", "cas_statement"))


def test_auto_unknown_and_garbage_replies_are_handled(monkeypatch):
    c, _ = boot(monkeypatch)
    for reply, expect in (('{"doc_type":"unknown"}', "unknown"), ("not json at all", "unknown"), ('{"doc_type":"passport"}', "unknown")):
        async def fake_generate(*a, _r=reply, **k):
            return _r

        monkeypatch.setattr(documents, "generate", fake_generate)
        res = c.post("/api/v1/documents/upload", files={"file": ("p.pdf", pdf(), "application/pdf")})
        assert res.status_code == 200 and res.json()["doc_type"] == expect


def test_explicit_type_skips_detection_and_uses_its_own_prompt(monkeypatch):
    c, _ = boot(monkeypatch)
    calls = []

    async def fake_generate(data, media_type, prompt, *, creds, **kw):
        calls.append(prompt)
        return '{"doc_type":"form16","gross_salary":1}'

    monkeypatch.setattr(documents, "generate", fake_generate)
    res = c.post("/api/v1/documents/upload", data={"doc_type": "form16"}, files={"file": ("f.pdf", pdf(), "application/pdf")})
    assert res.json()["doc_type"] == "form16" and len(calls) == 1 and "Form 16" in calls[0]


def test_statement_and_card_imports_also_surface_quota_cleanly(monkeypatch):
    from routers import cards, transactions
    c, db = boot(monkeypatch, credit_cards=[{"id": "55555555-5555-5555-5555-555555555555", "user_id": ME, "bank_name": "HDFC", "last4": "7777"}])
    for mod in (cards, transactions):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)

    async def fake(*a, **k):
        raise FakeGeminiError(REAL_429)

    monkeypatch.setattr(ai, "_gemini", fake)
    files = {"file": ("s.pdf", pdf(), "application/pdf")}
    for path in ("/api/v1/transactions/import", "/api/v1/credit-cards/55555555-5555-5555-5555-555555555555/statements/import"):
        res = c.post(path, files=files)
        assert res.status_code == 429 and res.json()["detail"].startswith("AI_QUOTA"), path
