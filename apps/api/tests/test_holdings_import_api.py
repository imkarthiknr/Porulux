import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import main
from core import crud
from core.auth import AuthUser, get_auth_user
from routers import holdings_import, insights
from services import ai, credentials
from tests.fakedb import FakeDB

ME = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000c"
USER = AuthUser(ME, datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")

ZERODHA_CSV = b"""Instrument,Qty.,Avg. cost,LTP,Invested,Cur. val
INFY,10,1450.50,1500.00,14505.00,15000.00
RELIANCE,5,2400,2500,12000,12500
NIFTYBEES,100,250.10,262.00,25010,26200
"""


def boot(monkeypatch, **tables):
    db = FakeDB(**tables)
    for mod in (holdings_import, crud, insights, credentials):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    return TestClient(main.app), db


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    main.app.dependency_overrides.clear()


def holding(id_, symbol, source=None, owner=ME, **kw):
    return {"id": id_, "user_id": owner, "symbol": symbol, "name": symbol, "holding_type": "STOCK", "units": 1,
            "avg_buy_price": 1.0, "current_price": 1.0, "isin": None, "source": source,
            "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-01T00:00:00Z", **kw}


def pdf_bytes(password=None):
    w = PdfWriter()
    w.add_blank_page(100, 100)
    if password:
        w.encrypt(password)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def test_preview_csv_needs_no_key_and_saves_nothing(monkeypatch):
    c, db = boot(monkeypatch, holdings=[holding("11111111-1111-1111-1111-111111111111", "INFY")])
    res = c.post("/api/v1/investments/import/preview", files={"file": ("Zerodha_holdings.csv", ZERODHA_CSV, "text/csv")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "Zerodha"                                   # guessed from the file name
    assert body["counts"] == {"new": 2, "update": 1, "unchanged": 0}     # INFY adopted (it had no source)
    assert body["totals"]["invested"] == pytest.approx(14505 + 12000 + 25010)
    assert len(db.tables["holdings"]) == 1                               # preview must not write


def test_explicit_source_overrides_the_guess(monkeypatch):
    c, _ = boot(monkeypatch)
    res = c.post("/api/v1/investments/import/preview", data={"source": "My Broker"},
                 files={"file": ("Zerodha_holdings.csv", ZERODHA_CSV, "text/csv")})
    assert res.json()["source"] == "My Broker"


def test_preview_errors_are_helpful(monkeypatch):
    c, _ = boot(monkeypatch)
    nothing = c.post("/api/v1/investments/import/preview", files={"file": ("a.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert nothing.status_code == 422 and "No holdings found" in nothing.json()["detail"]
    xls = c.post("/api/v1/investments/import/preview", files={"file": ("old.xls", b"x", "application/vnd.ms-excel")})
    assert xls.status_code == 415 and "xlsx" in xls.json()["detail"]
    assert c.post("/api/v1/investments/import/preview", files={"file": ("a.zip", b"x", "application/zip")}).status_code == 415


def test_pdf_preview_blocked_without_key_then_works_with_shared_key(monkeypatch):
    c, _ = boot(monkeypatch)
    monkeypatch.delenv("SHARED_KEY_CUTOFF", raising=False)
    blocked = c.post("/api/v1/investments/import/preview", files={"file": ("cas.pdf", pdf_bytes(), "application/pdf")})
    assert blocked.status_code == 402 and blocked.json()["detail"].startswith("AI_KEY_REQUIRED")

    monkeypatch.setenv("SHARED_KEY_CUTOFF", "2026-10-03T00:00:00Z")
    monkeypatch.setenv("GEMINI_API_KEY", "shared")

    async def fake_generate(*a, **k):
        return ('{"source":"NSDL CAS","holdings":[{"name":"Axis Bluechip Fund - Direct - Growth","isin":"INF846K01DP8",'
                '"units":100,"invested_value":5000,"current_value":7000,"type":"MF"}]}')

    monkeypatch.setattr(ai, "generate", fake_generate)
    ok = c.post("/api/v1/investments/import/preview", files={"file": ("cas.pdf", pdf_bytes(), "application/pdf")})
    assert ok.status_code == 200 and ok.json()["source"] == "NSDL CAS" and ok.json()["entries"][0]["holding_type"] == "MF"


def test_locked_pdf_asks_for_password(monkeypatch):
    c, _ = boot(monkeypatch)
    res = c.post("/api/v1/investments/import/preview", files={"file": ("cas.pdf", pdf_bytes("pan+dob"), "application/pdf")})
    assert res.status_code == 422 and res.json()["detail"].startswith("PASSWORD_REQUIRED")


def row(**kw):
    return {"name": "Infosys Ltd", "symbol": "INFY", "holding_type": "STOCK", "units": 10,
            "avg_buy_price": 1450.5, "current_price": 1500, **kw}


def test_confirm_inserts_updates_removes_and_tags_source(monkeypatch):
    mine, theirs = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    sold, groww = "33333333-3333-3333-3333-333333333333", "44444444-4444-4444-4444-444444444444"
    c, db = boot(monkeypatch, holdings=[
        holding(mine, "INFY"),                         # hand-added, adopted by the import
        holding(theirs, "INFY", owner=OTHER),          # another user's row
        holding(sold, "SOLD", source="Zerodha"),
        holding(groww, "TCS", source="Groww"),
    ])
    res = c.post("/api/v1/investments/import/confirm", json={
        "source": "Zerodha",
        "rows": [row(existing_id=mine), row(name="Reliance", symbol="RELIANCE", units=5, avg_buy_price=2400, current_price=2500)],
        "remove_ids": [sold, groww],                   # Groww's must be refused: different source
    })
    assert res.status_code == 200 and res.json() == {"inserted": 1, "updated": 1, "removed": 1, "assumed_lots": 0}
    rows = {r["id"]: r for r in db.tables["holdings"]}
    assert rows[mine]["source"] == "Zerodha" and rows[mine]["units"] == 10 and rows[mine]["current_price"] == 1500
    assert sold not in rows and groww in rows and theirs in rows
    new = next(r for r in db.tables["holdings"] if r["symbol"] == "RELIANCE")
    assert new["user_id"] == ME and new["source"] == "Zerodha" and new["last_imported_at"]


def test_confirm_refuses_other_users_rows_and_bad_input(monkeypatch):
    theirs = "22222222-2222-2222-2222-222222222222"
    c, db = boot(monkeypatch, holdings=[holding(theirs, "INFY", owner=OTHER, units=7)])
    res = c.post("/api/v1/investments/import/confirm", json={"source": "Zerodha", "rows": [row(existing_id=theirs)]})
    assert res.status_code == 404 and db.tables["holdings"][0]["units"] == 7
    for bad in (row(units=-1), row(holding_type="CRYPTO"), row(isin="not-an-isin")):
        assert c.post("/api/v1/investments/import/confirm", json={"source": "Z", "rows": [bad]}).status_code == 422


def test_confirm_keeps_existing_price_when_statement_has_none(monkeypatch):
    hid = "11111111-1111-1111-1111-111111111111"
    c, db = boot(monkeypatch, holdings=[holding(hid, "INFY", current_price=1234.0)])
    c.post("/api/v1/investments/import/confirm", json={"source": "Z", "rows": [row(existing_id=hid, current_price=None)]})
    assert db.tables["holdings"][0]["current_price"] == 1234.0
