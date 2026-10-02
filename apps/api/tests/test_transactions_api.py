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
