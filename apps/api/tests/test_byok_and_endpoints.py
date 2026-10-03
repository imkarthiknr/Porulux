from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import main
from core import crud
from core.auth import AuthUser, get_auth_user, get_current_user
from routers import documents, insights, salary, settings, transactions
from services import ai, credentials
from tests.fakedb import FakeDB

CUTOFF = datetime(2026, 10, 3, tzinfo=timezone.utc)
OLD_USER = AuthUser("00000000-0000-0000-0000-00000000000a", datetime(2026, 9, 1, tzinfo=timezone.utc))
NEW_USER = AuthUser("00000000-0000-0000-0000-00000000000b", datetime(2026, 10, 5, tzinfo=timezone.utc))

GOOD_KEY = "AIzaSy" + "x" * 33


def boot(monkeypatch, user, **tables):
    db = FakeDB(**tables)
    for mod in (crud, insights, salary, settings, credentials, transactions):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())
    monkeypatch.setenv("SHARED_KEY_CUTOFF", CUTOFF.isoformat())
    monkeypatch.setenv("GEMINI_API_KEY", "owner-shared-key")
    main.app.dependency_overrides[get_auth_user] = lambda: user
    return TestClient(main.app), db


@pytest.fixture(autouse=True)
def _clean():
    yield
    main.app.dependency_overrides.clear()


# ── bring-your-own key ────────────────────────────────────────────────────────

def _pdf() -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(100, 100)
    buf = io.BytesIO(); w.write(buf)
    return buf.getvalue()


PDF = {"file": ("s.pdf", _pdf(), "application/pdf")}


def test_new_user_without_key_is_blocked_from_ai_extraction(monkeypatch):
    c, _ = boot(monkeypatch, NEW_USER)
    res = c.post("/api/v1/documents/upload", files=PDF)
    assert res.status_code == 402 and res.json()["detail"].startswith("AI_KEY_REQUIRED")


def test_new_user_without_key_is_blocked_from_pdf_statement_import(monkeypatch):
    c, _ = boot(monkeypatch, NEW_USER)
    res = c.post("/api/v1/transactions/import", files=PDF)
    assert res.status_code == 402 and res.json()["detail"].startswith("AI_KEY_REQUIRED")


def test_csv_import_needs_no_key_even_for_new_user(monkeypatch):
    c, db = boot(monkeypatch, NEW_USER)
    csv = b"Date,Narration,Debit,Credit\n01/04/24,SWIGGY,100.00,\n"
    res = c.post("/api/v1/transactions/import", files={"file": ("s.csv", csv, "text/csv")})
    assert res.status_code == 201 and res.json()["inserted"] == 1


def test_existing_user_uses_shared_key(monkeypatch):
    c, _ = boot(monkeypatch, OLD_USER)
    seen = {}

    async def fake_generate(data, media_type, prompt, *, creds, **kw):
        seen["creds"] = creds
        return "unknown"

    monkeypatch.setattr(documents, "generate", fake_generate)
    res = c.post("/api/v1/documents/upload", files=PDF)
    assert res.status_code == 200
    assert seen["creds"].shared and seen["creds"].api_key == "owner-shared-key"


def test_saved_key_is_encrypted_never_returned_and_is_used(monkeypatch):
    c, db = boot(monkeypatch, NEW_USER)

    async def ok(provider, key):
        return None

    monkeypatch.setattr(ai, "validate_key", ok)
    saved = c.put("/api/v1/settings/ai-key", json={"provider": "gemini", "api_key": GOOD_KEY})
    assert saved.status_code == 200
    assert saved.json() == {"mode": "own", "provider": "gemini", "key_last4": GOOD_KEY[-4:]}
    assert GOOD_KEY not in saved.text

    stored = db.tables["user_ai_keys"][0]
    assert GOOD_KEY not in stored["encrypted_key"] and stored["user_id"] == "00000000-0000-0000-0000-00000000000b"
    assert c.get("/api/v1/settings/ai").json()["mode"] == "own"

    seen = {}

    async def fake_generate(data, media_type, prompt, *, creds, **kw):
        seen["creds"] = creds
        return "unknown"

    monkeypatch.setattr(documents, "generate", fake_generate)
    assert c.post("/api/v1/documents/upload", files=PDF).status_code == 200
    assert seen["creds"].api_key == GOOD_KEY and not seen["creds"].shared and seen["creds"].provider == "gemini"


def test_rejected_key_is_not_saved(monkeypatch):
    c, db = boot(monkeypatch, NEW_USER)

    async def reject(provider, key):
        raise ai.AIKeyError(provider)

    monkeypatch.setattr(ai, "validate_key", reject)
    res = c.put("/api/v1/settings/ai-key", json={"provider": "anthropic", "api_key": "sk-ant-" + "y" * 30})
    assert res.status_code == 400 and "Claude rejected" in res.json()["detail"]
    assert db.tables.get("user_ai_keys", []) == []


def test_provider_rejection_mid_upload_points_to_settings(monkeypatch):
    c, _ = boot(monkeypatch, OLD_USER)

    async def boom(*a, **k):
        raise ai.AIKeyError("gemini")

    monkeypatch.setattr(documents, "generate", boom)
    res = c.post("/api/v1/documents/upload", files=PDF)
    assert res.status_code == 402 and res.json()["detail"].startswith("AI_KEY_INVALID")


def test_delete_key_reverts_status(monkeypatch):
    c, db = boot(monkeypatch, NEW_USER, user_ai_keys=[{"user_id": "00000000-0000-0000-0000-00000000000b", "provider": "gemini", "encrypted_key": "x", "key_last4": "abcd"}])
    assert c.delete("/api/v1/settings/ai-key").status_code == 204
    assert c.get("/api/v1/settings/ai").json()["mode"] == "none"


def test_nobody_is_grandfathered_when_cutoff_unset(monkeypatch):
    c, _ = boot(monkeypatch, OLD_USER)
    monkeypatch.delenv("SHARED_KEY_CUTOFF")
    assert c.get("/api/v1/settings/ai").json()["mode"] == "none"


def test_fernet_roundtrip_and_rotated_secret_fails_cleanly(monkeypatch):
    from services import keyvault
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())
    token = keyvault.encrypt("secret-123")
    assert keyvault.decrypt(token) == "secret-123"
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", Fernet.generate_key().decode())  # rotated
    with pytest.raises(keyvault.KeyVaultError):
        keyvault.decrypt(token)


# ── salary edit ───────────────────────────────────────────────────────────────

def test_salary_edit_and_conflict(monkeypatch):
    rows = [
        {"id": "11111111-1111-1111-1111-111111111111", "user_id": "00000000-0000-0000-0000-00000000000a", "month": 5, "year": 2026, "net_pay": 100.0, "created_at": "2026-10-02T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z"},
        {"id": "22222222-2222-2222-2222-222222222222", "user_id": "00000000-0000-0000-0000-00000000000c", "month": 5, "year": 2026, "net_pay": 1.0, "created_at": "2026-10-02T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z"},
    ]
    c, db = boot(monkeypatch, OLD_USER, salary_records=rows)
    ok = c.patch("/api/v1/salary/11111111-1111-1111-1111-111111111111", json={"net_pay": 136021, "gross_pay": 191238})
    assert ok.status_code == 200 and ok.json()["net_pay"] == 136021
    assert db.tables["salary_records"][0]["net_pay"] == 136021
    assert c.patch("/api/v1/salary/22222222-2222-2222-2222-222222222222", json={"net_pay": 5}).status_code == 404  # other user's row untouched
    assert db.tables["salary_records"][1]["net_pay"] == 1.0
    assert c.patch("/api/v1/salary/11111111-1111-1111-1111-111111111111", json={}).status_code == 400


# ── trend / recurring ─────────────────────────────────────────────────────────

def _month(back, day=10):
    t = date.today().replace(day=1)
    idx = t.year * 12 + t.month - 1 - back
    return date(idx // 12, idx % 12 + 1, day).isoformat()


def test_trend_aggregates_per_month_and_skips_opening_balance(monkeypatch):
    txns = [
        {"user_id": "00000000-0000-0000-0000-00000000000a", "transaction_date": _month(0), "description": "salary", "amount": 100000, "category": "Salary"},
        {"user_id": "00000000-0000-0000-0000-00000000000a", "transaction_date": _month(0), "description": "rent", "amount": -30000, "category": "Rent"},
        {"user_id": "00000000-0000-0000-0000-00000000000a", "transaction_date": _month(1), "description": "swiggy", "amount": -500, "category": "Food"},
        {"user_id": "00000000-0000-0000-0000-00000000000a", "transaction_date": _month(1), "description": "open", "amount": 999999, "category": "Opening Balance"},
        {"user_id": "00000000-0000-0000-0000-00000000000c", "transaction_date": _month(0), "description": "x", "amount": -777, "category": "Food"},
    ]
    c, _ = boot(monkeypatch, OLD_USER, bank_transactions=txns)
    data = c.get("/api/v1/transactions/trend?months=3").json()
    assert [m["month"] for m in data["months"]] == sorted(m["month"] for m in data["months"]) and len(data["months"]) == 3
    this, last = data["months"][-1], data["months"][-2]
    assert (this["income"], this["expenses"]) == (100000, 30000)
    assert (last["income"], last["expenses"]) == (0, 500)          # opening balance not counted as income
    assert data["top_categories"][0] == "Rent"


def test_recurring_endpoint_finds_netflix(monkeypatch):
    txns = [
        {"user_id": "00000000-0000-0000-0000-00000000000a", "transaction_date": _month(i, 5), "description": f"UPI-NETFLIX-netflix@ybl-{i}", "amount": -649, "category": "Shopping"}
        for i in range(5)
    ]
    c, _ = boot(monkeypatch, OLD_USER, bank_transactions=txns)
    data = c.get("/api/v1/transactions/recurring").json()
    assert [i["name"] for i in data["items"]] == ["Netflix"]
    assert data["monthly_commitments"] == 649


# ── investments / loans ───────────────────────────────────────────────────────

def test_investment_returns_with_and_without_lots(monkeypatch):
    holdings = [
        {"id": "h1", "user_id": "00000000-0000-0000-0000-00000000000a", "symbol": "INFY", "name": "Infosys", "holding_type": "STOCK", "units": 10, "current_price": 1200, "avg_buy_price": None},
        {"id": "h2", "user_id": "00000000-0000-0000-0000-00000000000a", "symbol": "NIFTY", "name": "Nifty ETF", "holding_type": "ETF", "units": 100, "current_price": 150, "avg_buy_price": 100},
    ]
    one_year_ago = (date.today() - timedelta(days=365)).isoformat()
    lots = [{"id": "l1", "user_id": "00000000-0000-0000-0000-00000000000a", "holding_id": "h1", "lot_date": one_year_ago, "lot_type": "BUY", "units": 10, "price": 1000}]
    c, _ = boot(monkeypatch, OLD_USER, holdings=holdings, holding_lots=lots)
    data = c.get("/api/v1/investments/returns").json()
    infy = next(h for h in data["holdings"] if h["symbol"] == "INFY")
    assert infy["xirr_pct"] == pytest.approx(20.0, abs=0.1) and infy["absolute_return_pct"] == 20.0
    etf = next(h for h in data["holdings"] if h["symbol"] == "NIFTY")
    assert etf["xirr_pct"] is None and etf["absolute_return_pct"] == 50.0   # no dated lots -> no XIRR
    assert data["portfolio"]["invested"] == 20000 and data["portfolio"]["current_value"] == 27000


def test_lot_requires_own_holding(monkeypatch):
    c, _ = boot(monkeypatch, OLD_USER, holdings=[{"id": "h9", "user_id": "00000000-0000-0000-0000-00000000000c"}])
    res = c.post("/api/v1/holdings/h9/lots", json={"lot_date": "2024-01-01", "units": 1, "price": 10})
    assert res.status_code == 404


def test_loan_tracker_needs_details_then_builds_schedule(monkeypatch):
    loans = [
        {"id": "L1", "user_id": "00000000-0000-0000-0000-00000000000a", "loan_type": "HOME_LOAN", "lender_name": "HDFC", "outstanding_amount": 4000000, "emi_amount": None, "interest_rate": None, "tenure_months": None, "start_date": None, "principal_amount": None},
    ]
    c, db = boot(monkeypatch, OLD_USER, loans=loans)
    res = c.get("/api/v1/loan-tracker/L1")
    assert res.status_code == 422 and "interest rate" in res.json()["detail"]

    db.tables["loans"][0].update(interest_rate=8.5, tenure_months=240, start_date="2022-04-01", principal_amount=5000000)
    data = c.get("/api/v1/loan-tracker/L1").json()
    assert data["tax_applicable"] and len(data["schedule"]) == 240
    assert data["summary"]["emi"] == pytest.approx(43391.16, abs=0.01)
    assert data["summary"]["outstanding_principal"] < 5000000
    assert c.get("/api/v1/loan-tracker/nope").status_code == 404
