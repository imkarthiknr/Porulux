"""A tiny in-memory stand-in for the supabase-py query builder, enough for these routers."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

_DEFAULTS = {"created_at": "2026-10-02T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z"}


class Query:
    def __init__(self, db: "FakeDB", table: str):
        self.db, self.table = db, table
        self.op, self.payload, self.filters, self._limit = "select", None, [], None
        self.on_conflict = None

    # builders
    def select(self, *_): self.op = "select"; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def upsert(self, row, on_conflict=None): self.op, self.payload, self.on_conflict = "upsert", row, on_conflict; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.filters.append((k, "eq", v)); return self
    def gte(self, k, v): self.filters.append((k, "gte", v)); return self
    def lte(self, k, v): self.filters.append((k, "lte", v)); return self
    def lt(self, k, v): self.filters.append((k, "lt", v)); return self
    def order(self, *_, **__): return self
    def limit(self, n): self._limit = n; return self
    def maybe_single(self): self._limit = 1; return self

    def _match(self, row):
        for k, kind, v in self.filters:
            x = row.get(k)
            if x is None:
                return False
            if kind == "eq" and x != v: return False
            if kind == "gte" and not x >= v: return False
            if kind == "lte" and not x <= v: return False
            if kind == "lt" and not x < v: return False
        return True

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            made = [{"id": str(uuid.uuid4()), **_DEFAULTS, **i} for i in items]
            rows.extend(made)
            return SimpleNamespace(data=made)
        if self.op == "upsert":
            key = self.on_conflict
            for r in rows:
                if key and r.get(key) == self.payload.get(key):
                    r.update(self.payload)
                    return SimpleNamespace(data=[r])
            row = {"id": str(uuid.uuid4()), **_DEFAULTS, **self.payload}
            rows.append(row)
            return SimpleNamespace(data=[row])
        match = [r for r in rows if self._match(r)]
        if self.op == "update":
            for r in match:
                r.update(self.payload)
            return SimpleNamespace(data=match)
        if self.op == "delete":
            for r in match:
                rows.remove(r)
            return SimpleNamespace(data=match)
        return SimpleNamespace(data=match[: self._limit] if self._limit else match)


class FakeDB:
    def __init__(self, **tables):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name: str) -> Query:
        return Query(self, name)
