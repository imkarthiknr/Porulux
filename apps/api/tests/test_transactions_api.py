from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import get_current_user
from routers import transactions

CSV = b"""Date,Narration,Debit,Credit
01/04/24,SWIGGY ORDER,300.00,
01/04/24,SWIGGY ORDER,300.00,
02/04/24,ACME SALARY,,100000.00
"""


class FakeQuery:
    def __init__(self, store, existing):
        self.store, self.existing, self.inserted = store, existing, None

    def select(self, *_): return self
    def eq(self, *_): return self
    def gte(self, *_): return self
    def lte(self, *_): return self
    def limit(self, *_): return self
    def lt(self, *_): return self
    def order(self, *_, **__): return self

    def insert(self, rows):
        self.inserted = rows
        self.store.extend(rows)
        return self

    def execute(self):
        return SimpleNamespace(data=self.inserted if self.inserted is not None else self.existing)


class FakeClient:
    def __init__(self, existing=()):
        self.store, self.existing = [], list(existing)

    def table(self, _):
        return FakeQuery(self.store, self.existing)


@pytest.fixture
def api(monkeypatch):
    main.app.dependency_overrides[get_current_user] = lambda: "user-1"
    holder = {}

    def install(client):
        holder["client"] = client
        monkeypatch.setattr(transactions, "get_supabase_client", lambda: client)
        return TestClient(main.app)

    yield install
    main.app.dependency_overrides.clear()


def test_import_categorises_and_keeps_same_day_duplicates_within_file(api):
    fake = FakeClient()
    res = api(fake).post("/api/v1/transactions/import", files={"file": ("s.csv", CSV, "text/csv")})
    assert res.status_code == 201
    assert res.json() == {"parsed": 3, "inserted": 3, "duplicates_skipped": 0}
    assert sorted(r["category"] for r in fake.store) == ["Food", "Food", "Salary"]
    assert {r["user_id"] for r in fake.store} == {"user-1"}


def test_reimport_skips_existing_rows(api):
    existing = [
        {"transaction_date": "2024-04-01", "description": "SWIGGY ORDER", "amount": -300.0},
        {"transaction_date": "2024-04-02", "description": "ACME SALARY", "amount": 100000.0},
    ]
    fake = FakeClient(existing)
    res = api(fake).post("/api/v1/transactions/import", files={"file": ("s.csv", CSV, "text/csv")})
    assert res.json() == {"parsed": 3, "inserted": 1, "duplicates_skipped": 2}


def test_unsupported_type_rejected(api):
    res = api(FakeClient()).post("/api/v1/transactions/import", files={"file": ("a.zip", b"x", "application/zip")})
    assert res.status_code == 415


def test_bad_csv_returns_422(api):
    res = api(FakeClient()).post("/api/v1/transactions/import", files={"file": ("a.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert res.status_code == 422


def test_trailing_slash_is_equivalent_and_never_redirects(api):
    client = api(FakeClient())
    for path in ("/api/v1/transactions/categories", "/api/v1/transactions/categories/"):
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 200
    # collection routes: slash or not, no 307
    for path in ("/api/v1/transactions", "/api/v1/transactions/"):
        assert client.get(path, follow_redirects=False).status_code == 200


CSV_WITH_BALANCE = b"""Date,Narration,Debit,Credit,Balance
01/04/24,SWIGGY ORDER,300.00,,9700.00
02/04/24,ACME SALARY,,100000.00,109700.00
"""


def test_first_import_seeds_opening_balance_but_not_counted_as_inserted(api):
    fake = FakeClient()
    res = api(fake).post("/api/v1/transactions/import", files={"file": ("s.csv", CSV_WITH_BALANCE, "text/csv")})
    assert res.json() == {"parsed": 2, "inserted": 2, "duplicates_skipped": 0}
    opening = [r for r in fake.store if r["category"] == "Opening Balance"]
    assert len(opening) == 1 and opening[0]["amount"] == 10000.00
    # running total of everything equals the real closing balance
    assert round(sum(r["amount"] for r in fake.store), 2) == 109700.00


def test_no_opening_balance_when_user_already_has_transactions(api):
    fake = FakeClient([{"id": "x", "transaction_date": "2024-03-01", "description": "old", "amount": 5.0}])
    api(fake).post("/api/v1/transactions/import", files={"file": ("s.csv", CSV_WITH_BALANCE, "text/csv")})
    assert not [r for r in fake.store if r["category"] == "Opening Balance"]


def test_protected_pdf_asks_for_password_instead_of_calling_ai(api, monkeypatch):
    import io
    from pypdf import PdfWriter

    w = PdfWriter(); w.add_blank_page(100, 100); w.encrypt("pw")
    buf = io.BytesIO(); w.write(buf)

    async def boom(*a, **k):
        raise AssertionError("AI must not be called for a locked PDF")

    monkeypatch.setattr(transactions.ai, "extract_transactions", boom)
    res = api(FakeClient()).post("/api/v1/transactions/import", files={"file": ("s.pdf", buf.getvalue(), "application/pdf")})
    assert res.status_code == 422 and res.json()["detail"].startswith("PASSWORD_REQUIRED")
