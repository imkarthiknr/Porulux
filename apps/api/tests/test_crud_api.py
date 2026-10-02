from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from core import crud
from core.auth import get_current_user


class FakeQuery:
    def __init__(self, db):
        self.db, self.op, self.payload, self.filters = db, "select", None, {}

    def select(self, *_): self.op = "select"; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.filters[k] = v; return self
    def order(self, *_, **__): return self

    def execute(self):
        rows = self.db.rows
        match = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.op == "insert":
            row = {"id": "33333333-3333-3333-3333-333333333333", "created_at": "2026-10-02T00:00:00Z",
                   "updated_at": "2026-10-02T00:00:00Z", "as_of_date": "2026-10-02", **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row])
        if self.op == "update":
            for r in match: r.update(self.payload)
            return SimpleNamespace(data=match)
        if self.op == "delete":
            for r in match: rows.remove(r)
            return SimpleNamespace(data=match)
        return SimpleNamespace(data=match)


class FakeDB:
    def __init__(self): self.rows = []
    def table(self, _): return FakeQuery(self)


@pytest.fixture
def client(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(crud, "get_supabase_client", lambda: db)
    main.app.dependency_overrides[get_current_user] = lambda: "user-1"
    yield TestClient(main.app), db
    main.app.dependency_overrides.clear()


@pytest.mark.parametrize("path,body", [
    ("/api/v1/holdings", {"symbol": "INFY", "name": "Infosys", "holding_type": "STOCK", "units": 10, "current_price": 1500}),
    ("/api/v1/loans", {"loan_type": "HOME_LOAN", "lender_name": "HDFC", "outstanding_amount": 4500000}),
    ("/api/v1/epf-nps", {"account_type": "EPF", "balance": 250000}),
])
def test_create_list_update_delete(client, path, body):
    c, db = client
    created = c.post(path, json=body)
    assert created.status_code == 201, created.text
    assert db.rows[0]["user_id"] == "user-1"

    assert len(c.get(path).json()) == 1
    assert len(c.get(path + "/").json()) == 1   # trailing slash behaves the same

    key = next(iter(body))
    patched = c.patch(f"{path}/{created.json()['id']}", json={key: body[key]})
    assert patched.status_code == 200, patched.text

    assert c.delete(f"{path}/{created.json()['id']}").status_code == 204
    assert c.get(path).json() == []


def test_validation_error_is_422_with_field_info(client):
    c, _ = client
    res = c.post("/api/v1/holdings", json={"symbol": "X"})
    assert res.status_code == 422
    assert any("name" in e["loc"] for e in res.json()["detail"])
