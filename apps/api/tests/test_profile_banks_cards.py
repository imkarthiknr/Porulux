import io
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import main
from core import crud
from core.auth import AuthUser, get_auth_user
from routers import bank_accounts, cards, insights, networth, profile, transactions
from services import ai, card_import, credentials
from services.cards import card_overview, next_due_date, total_card_dues, upcoming_dues
from tests.fakedb import FakeDB

ME = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000c"
USER = AuthUser(ME, datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class FakeStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def from_(self, bucket):
        assert bucket == "avatars"
        return self

    def upload(self, path, data, opts=None):
        self.files[path] = data

    def remove(self, paths):
        for p in paths:
            self.files.pop(p, None)

    def create_signed_url(self, path, seconds):
        if path not in self.files:
            raise KeyError(path)
        return {"signedURL": f"/object/sign/avatars/{path}?token=t"}


class FakeClient(FakeDB):
    def __init__(self, **tables):
        super().__init__(**tables)
        self.storage = FakeStorage()


def boot(monkeypatch, **tables):
    db = FakeClient(**tables)
    for mod in (crud, profile, bank_accounts, cards, insights, networth, transactions, credentials):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    return TestClient(main.app), db


@pytest.fixture(autouse=True)
def _clean():
    yield
    main.app.dependency_overrides.clear()


# ── profile ───────────────────────────────────────────────────────────────────

def test_empty_profile_defaults_to_india(monkeypatch):
    c, _ = boot(monkeypatch)
    body = c.get("/api/v1/profile").json()
    assert body["country"] == "India" and body["avatar_url"] is None and body["email"] == "me@example.com"


def test_save_profile_trims_blanks_and_validates(monkeypatch):
    c, db = boot(monkeypatch)
    ok = c.put("/api/v1/profile", json={"full_name": "  Karthik N R ", "phone": "+91 98765 43210", "city": "Bengaluru", "state": " ", "postal_code": "560001", "country": "India"})
    assert ok.status_code == 200 and ok.json()["full_name"] == "Karthik N R" and ok.json()["state"] is None
    assert db.tables["profiles"][0]["user_id"] == ME
    assert c.put("/api/v1/profile", json={"phone": "abc"}).status_code == 422
    assert c.put("/api/v1/profile", json={"postal_code": "!!"}).status_code == 422


def test_avatar_upload_replace_and_delete(monkeypatch):
    c, db = boot(monkeypatch)
    first = c.post("/api/v1/profile/avatar", files={"file": ("me.png", PNG, "image/png")})
    assert first.status_code == 200 and "token=t" in first.json()["avatar_url"]
    assert first.json()["avatar_url"].startswith("https://proj.supabase.co/storage/v1/object/sign/")
    assert len(db.storage.files) == 1

    monkeypatch.setattr(profile.time, "time", lambda: 9999999999)  # force a new key
    second = c.post("/api/v1/profile/avatar", files={"file": ("me.jpg", JPEG, "image/jpeg")})
    assert second.status_code == 200 and len(db.storage.files) == 1   # old photo removed

    gone = c.delete("/api/v1/profile/avatar")
    assert gone.json()["avatar_url"] is None and db.storage.files == {}


def test_avatar_rejects_fake_images_and_big_files(monkeypatch):
    c, _ = boot(monkeypatch)
    assert c.post("/api/v1/profile/avatar", files={"file": ("x.png", b"<?php evil ?>", "image/png")}).status_code == 415
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    assert c.post("/api/v1/profile/avatar", files={"file": ("x.png", big, "image/png")}).status_code == 413


# ── bank accounts ─────────────────────────────────────────────────────────────

ACC = {"bank_name": "HDFC Bank", "last4": "4321", "account_type": "SAVINGS", "nickname": "Salary a/c"}


def test_bank_account_crud_and_validation(monkeypatch):
    c, db = boot(monkeypatch)
    assert c.post("/api/v1/bank-accounts", json={**ACC, "last4": "12"}).status_code == 422
    assert c.post("/api/v1/bank-accounts", json={**ACC, "ifsc": "BAD"}).status_code == 422
    ok = c.post("/api/v1/bank-accounts", json={**ACC, "ifsc": "HDFC0001234"})
    assert ok.status_code == 201 and db.tables["bank_accounts"][0]["user_id"] == ME
    assert len(c.get("/api/v1/bank-accounts").json()) == 1


def test_summary_balances_and_assign_unassigned(monkeypatch):
    acc_id = "11111111-1111-1111-1111-111111111111"
    other_acc = "22222222-2222-2222-2222-222222222222"
    txns = [
        {"id": "t1", "user_id": ME, "account_id": acc_id, "amount": 1000.0, "transaction_date": "2026-09-01"},
        {"id": "t2", "user_id": ME, "account_id": acc_id, "amount": -250.0, "transaction_date": "2026-09-10"},
        {"id": "t3", "user_id": ME, "account_id": None, "amount": 500.0, "transaction_date": "2026-09-05"},
        {"id": "t4", "user_id": OTHER, "account_id": None, "amount": 99999.0, "transaction_date": "2026-09-05"},
    ]
    accounts = [
        {"id": acc_id, "user_id": ME, "bank_name": "HDFC Bank", "last4": "4321", "account_type": "SAVINGS"},
        {"id": other_acc, "user_id": ME, "bank_name": "SBI", "last4": "9999", "account_type": "SAVINGS"},
    ]
    c, db = boot(monkeypatch, bank_accounts=accounts, bank_transactions=txns)
    s = c.get("/api/v1/bank-accounts/summary").json()
    hdfc = next(a for a in s["accounts"] if a["last4"] == "4321")
    assert hdfc["balance"] == 750 and hdfc["transaction_count"] == 2 and hdfc["last_transaction_date"] == "2026-09-10"
    assert s["unassigned"] == {"count": 1, "balance": 500.0} and s["total_balance"] == 1250

    assert c.post(f"/api/v1/bank-accounts/{other_acc}/assign-unassigned").json() == {"assigned": 1}
    t3 = next(t for t in db.tables["bank_transactions"] if t["id"] == "t3")
    assert t3["account_id"] == other_acc and t3["bank_name"] == "SBI"
    assert next(t for t in db.tables["bank_transactions"] if t["id"] == "t4")["account_id"] is None   # other user's row untouched


def test_import_into_account_tags_rows_scopes_dedupe_and_opening_balance(monkeypatch):
    acc = "11111111-1111-1111-1111-111111111111"
    csv = b"Date,Narration,Debit,Credit,Balance\n01/04/24,SWIGGY,300.00,,9700.00\n02/04/24,SALARY,,100000.00,109700.00\n"
    existing_other_account = {"id": "x", "user_id": ME, "account_id": "33333333-3333-3333-3333-333333333333",
                              "transaction_date": "2024-03-01", "description": "old", "amount": 5.0}
    c, db = boot(monkeypatch,
                 bank_accounts=[{"id": acc, "user_id": ME, "bank_name": "HDFC Bank", "last4": "4321"}],
                 bank_transactions=[existing_other_account])
    res = c.post("/api/v1/transactions/import", data={"account_id": acc}, files={"file": ("s.csv", csv, "text/csv")})
    assert res.status_code == 201 and res.json()["inserted"] == 2
    new = [r for r in db.tables["bank_transactions"] if r.get("account_id") == acc]
    assert len(new) == 3                                           # 2 rows + this account's opening balance
    assert {r["bank_name"] for r in new} == {"HDFC Bank"} and {r["account_last4"] for r in new} == {"4321"}
    assert any(r["category"] == "Opening Balance" and r["amount"] == 10000 for r in new)

    again = c.post("/api/v1/transactions/import", data={"account_id": acc}, files={"file": ("s.csv", csv, "text/csv")})
    assert again.json()["duplicates_skipped"] == 2 and again.json()["inserted"] == 0


def test_import_rejects_someone_elses_account(monkeypatch):
    c, _ = boot(monkeypatch, bank_accounts=[{"id": "44444444-4444-4444-4444-444444444444", "user_id": OTHER, "bank_name": "X", "last4": "1111"}])
    csv = b"Date,Narration,Debit,Credit\n01/04/24,A,1.00,\n"
    res = c.post("/api/v1/transactions/import", data={"account_id": "44444444-4444-4444-4444-444444444444"}, files={"file": ("s.csv", csv, "text/csv")})
    assert res.status_code == 404


def test_list_filters_by_account_and_unassigned(monkeypatch):
    a = "11111111-1111-1111-1111-111111111111"
    base = {"user_id": ME, "description": "d", "created_at": "2026-10-01T00:00:00Z", "category": "Food"}
    txns = [
        {**base, "id": "00000000-0000-0000-0000-000000000001", "transaction_date": "2026-10-02", "amount": -1.0, "account_id": a},
        {**base, "id": "00000000-0000-0000-0000-000000000002", "transaction_date": "2026-10-03", "amount": -2.0, "account_id": None},
    ]
    c, _ = boot(monkeypatch, bank_transactions=txns)
    assert [t["amount"] for t in c.get(f"/api/v1/transactions?month=2026-10&account_id={a}").json()] == [-1.0]
    assert [t["amount"] for t in c.get("/api/v1/transactions?month=2026-10&account_id=unassigned").json()] == [-2.0]
    assert len(c.get("/api/v1/transactions?month=2026-10").json()) == 2


# ── credit cards ──────────────────────────────────────────────────────────────

CARD = {"bank_name": "HDFC Bank", "card_name": "Regalia", "network": "VISA", "last4": "7777", "credit_limit": 300000, "statement_day": 15, "due_day": 5}
CARD_ID = "55555555-5555-5555-5555-555555555555"


def stmt_pdf() -> bytes:
    w = PdfWriter(); w.add_blank_page(100, 100)
    b = io.BytesIO(); w.write(b)
    return b.getvalue()


def test_card_crud_validation_and_duplicates(monkeypatch):
    c, db = boot(monkeypatch)
    assert c.post("/api/v1/credit-cards", json={**CARD, "last4": "7"}).status_code == 422
    assert c.post("/api/v1/credit-cards", json={**CARD, "due_day": 40}).status_code == 422
    assert c.post("/api/v1/credit-cards", json={**CARD, "network": "BITCOIN"}).status_code == 422
    assert c.post("/api/v1/credit-cards", json=CARD).status_code == 201
    assert db.tables["credit_cards"][0]["user_id"] == ME


def test_pure_overview_math():
    today = date(2026, 10, 3)
    card = {"id": "c1", "bank_name": "HDFC", "last4": "7777", "credit_limit": 100000, "due_day": 5}
    stmts = [
        {"statement_date": "2026-08-15", "total_due": 5000, "paid": True, "due_date": "2026-09-05"},
        {"statement_date": "2026-09-15", "total_due": 25000, "minimum_due": 1250, "paid": False, "due_date": "2026-10-05"},
    ]
    o = card_overview(card, stmts, today)
    assert o["outstanding"] == 25000 and o["utilization_pct"] == 25.0 and o["available_credit"] == 75000
    assert o["next_due"]["days_left"] == 2 and o["next_due"]["minimum_due"] == 1250 and not o["next_due"]["overdue"]
    assert upcoming_dues([o])[0]["label"] == "HDFC ···· 7777"

    paid = card_overview(card, [{**stmts[1], "paid": True}], today)
    assert paid["outstanding"] == 0 and paid["next_due"]["estimated"] and upcoming_dues([paid]) == []

    late = card_overview(card, stmts, date(2026, 10, 9))
    assert late["next_due"]["overdue"]
    assert total_card_dues({"c1": stmts, "c2": [{"statement_date": "2026-09-01", "total_due": 700, "paid": False}]}) == 25700


def test_next_due_date_clamps_and_rolls_over():
    assert next_due_date(31, date(2026, 2, 10)) == date(2026, 2, 28)
    assert next_due_date(5, date(2026, 12, 20)) == date(2027, 1, 5)
    assert next_due_date(5, date(2026, 10, 5)) == date(2026, 10, 5)


def test_csv_statement_import_creates_statement_and_categorises(monkeypatch):
    c, db = boot(monkeypatch, credit_cards=[{**CARD, "id": CARD_ID, "user_id": ME}])
    csv = b"Date,Description,Debit,Credit\n03/09/26,SWIGGY ORDER,500.00,\n05/09/26,AMAZON PAY,1500.00,\n20/09/26,PAYMENT RECEIVED,,1000.00\n"
    res = c.post(f"/api/v1/credit-cards/{CARD_ID}/statements/import", files={"file": ("c.csv", csv, "text/csv")})
    assert res.status_code == 201 and res.json()["transactions_inserted"] == 3
    stmt = db.tables["card_statements"][0]
    assert stmt["total_due"] == 1000 and stmt["source"] == "csv" and stmt["paid"] is False   # 500+1500-1000
    cats = {t["description"]: (t["amount"], t["category"]) for t in db.tables["card_transactions"]}
    assert cats["SWIGGY ORDER"] == (500.0, "Food") and cats["PAYMENT RECEIVED"] == (-1000.0, "Payment/Refund")

    again = c.post(f"/api/v1/credit-cards/{CARD_ID}/statements/import", files={"file": ("c.csv", csv, "text/csv")})
    assert again.status_code == 409


def test_ai_statement_import_validates_card_and_uses_user_key(monkeypatch):
    c, db = boot(monkeypatch, credit_cards=[{**CARD, "id": CARD_ID, "user_id": ME}])
    monkeypatch.setenv("SHARED_KEY_CUTOFF", "2026-10-03T00:00:00Z")
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    seen = {}

    async def fake_generate(data, media_type, prompt, *, creds, **kw):
        seen["creds"] = creds
        return ('{"card_last4":"7777","statement_date":"2026-09-15","period_start":"2026-08-16","period_end":"2026-09-15",'
                '"due_date":"2026-10-05","total_due":25000.5,"minimum_due":1250,"credit_limit":300000,'
                '"transactions":[{"date":"2026-09-01","description":"UBER TRIP","amount":450.5},{"date":"2026-09-10","description":"REFUND AMAZON","amount":-100}]}')

    monkeypatch.setattr(ai, "generate", fake_generate)
    res = c.post(f"/api/v1/credit-cards/{CARD_ID}/statements/import", files={"file": ("s.pdf", stmt_pdf(), "application/pdf")})
    assert res.status_code == 201, res.text
    assert seen["creds"].shared                                      # pre-cutoff account uses the shared key
    stmt = db.tables["card_statements"][0]
    assert stmt["due_date"] == "2026-10-05" and stmt["minimum_due"] == 1250 and stmt["total_due"] == 25000.5
    cats = {t["description"]: t["category"] for t in db.tables["card_transactions"]}
    assert cats == {"UBER TRIP": "Travel", "REFUND AMAZON": "Payment/Refund"}

    ov = c.get("/api/v1/credit-cards/overview").json()
    assert ov["totals"]["outstanding"] == 25000.5 and ov["cards"][0]["next_due"]["date"] == "2026-10-05"
    assert ov["upcoming_dues"] and ov["upcoming_dues"][0]["amount_due"] == 25000.5


def test_wrong_card_statement_is_rejected(monkeypatch):
    c, db = boot(monkeypatch, credit_cards=[{**CARD, "id": CARD_ID, "user_id": ME}])
    monkeypatch.setenv("SHARED_KEY_CUTOFF", "2026-10-03T00:00:00Z")
    monkeypatch.setenv("GEMINI_API_KEY", "shared")

    async def fake_generate(*a, **k):
        return '{"card_last4":"1234","statement_date":"2026-09-15","total_due":10,"transactions":[]}'

    monkeypatch.setattr(ai, "generate", fake_generate)
    res = c.post(f"/api/v1/credit-cards/{CARD_ID}/statements/import", files={"file": ("s.pdf", stmt_pdf(), "application/pdf")})
    assert res.status_code == 422 and "1234" in res.json()["detail"]
    assert db.tables.get("card_statements", []) == []


def test_statement_pdf_needs_key_for_new_user(monkeypatch):
    c, _ = boot(monkeypatch, credit_cards=[{**CARD, "id": CARD_ID, "user_id": ME}])
    monkeypatch.delenv("SHARED_KEY_CUTOFF", raising=False)
    res = c.post(f"/api/v1/credit-cards/{CARD_ID}/statements/import", files={"file": ("s.pdf", stmt_pdf(), "application/pdf")})
    assert res.status_code == 402 and res.json()["detail"].startswith("AI_KEY_REQUIRED")


def test_mark_paid_and_delete_statement_and_isolation(monkeypatch):
    sid, osid = "66666666-6666-6666-6666-666666666666", "77777777-7777-7777-7777-777777777777"
    c, db = boot(monkeypatch,
                 credit_cards=[{**CARD, "id": CARD_ID, "user_id": ME}],
                 card_statements=[
                     {"id": sid, "user_id": ME, "card_id": CARD_ID, "statement_date": "2026-09-15", "total_due": 100.0, "paid": False},
                     {"id": osid, "user_id": OTHER, "card_id": CARD_ID, "statement_date": "2026-09-15", "total_due": 5.0, "paid": False},
                 ])
    assert c.patch(f"/api/v1/credit-cards/statements/{sid}", json={"paid": True}).json()["paid"] is True
    assert c.patch(f"/api/v1/credit-cards/statements/{osid}", json={"paid": True}).status_code == 404
    assert c.delete(f"/api/v1/credit-cards/statements/{sid}").status_code == 204
    assert [s["id"] for s in db.tables["card_statements"]] == [osid]


def test_networth_includes_card_dues_as_liability(monkeypatch):
    c, _ = boot(monkeypatch,
                holdings=[], epf_nps_balances=[], bank_transactions=[{"user_id": ME, "amount": 1000.0}], loans=[{"user_id": ME, "outstanding_amount": 400.0}],
                card_statements=[
                    {"user_id": ME, "card_id": "c1", "statement_date": "2026-08-15", "total_due": 999.0, "paid": False},   # superseded
                    {"user_id": ME, "card_id": "c1", "statement_date": "2026-09-15", "total_due": 250.0, "paid": False},
                    {"user_id": ME, "card_id": "c2", "statement_date": "2026-09-15", "total_due": 80.0, "paid": True},
                ])
    snap = c.get("/api/v1/networth/snapshot").json()
    assert snap["breakdown"]["credit_cards"] == 250.0 and snap["total_liabilities"] == 650.0 and snap["net_worth"] == 350.0


def test_card_import_normalisation_edge_cases():
    parsed = card_import.normalize_ai_result({"statement_date": "15/09/2026", "total_due": 10, "card_last4": "XXXX-XXXX-XXXX-1234",
                                              "transactions": [{"date": "bad", "description": "x", "amount": 1}, {"date": "2026-09-01", "description": "ok", "amount": 5}]})
    assert parsed.card_last4 == "1234" and parsed.statement_date == date(2026, 9, 15) and len(parsed.transactions) == 1
    with pytest.raises(ValueError):
        card_import.normalize_ai_result({"transactions": []})
