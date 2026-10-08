from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from core.auth import AuthUser, get_auth_user
from routers import feedback

USER = AuthUser("00000000-0000-0000-0000-00000000000a", datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    feedback._recent.clear()
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _fake_github(monkeypatch, status_code=201):
    sent = {}

    class FakeClient:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, json, headers):
            sent.update(url=url, json=json, headers=headers)
            return httpx.Response(status_code, json={"number": 42}, request=httpx.Request("POST", url))

    monkeypatch.setattr(feedback.httpx, "AsyncClient", FakeClient)
    return sent


def test_creates_issue_without_leaking_identity(client, monkeypatch):
    sent = _fake_github(monkeypatch)
    r = client.post("/api/v1/feedback", json={"kind": "issue", "message": "Bank import fails on my PDF", "page": "/dashboard/banks"})
    assert r.status_code == 201 and r.json() == {"ok": True, "issue_number": 42}
    assert sent["url"] == "https://api.github.com/repos/o/r/issues"
    assert sent["json"]["labels"] == ["customer-feedback", "bug"]
    assert sent["json"]["title"].startswith("[Issue] Bank import fails")
    assert "me@example.com" not in sent["json"]["body"] and USER.id not in sent["json"]["body"]
    assert sent["headers"]["Authorization"] == "Bearer tok"


def test_not_configured(client, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN")
    assert client.post("/api/v1/feedback", json={"kind": "idea", "message": "Add a budgets page please"}).status_code == 503


def test_github_failure_is_502(client, monkeypatch):
    _fake_github(monkeypatch, status_code=403)
    assert client.post("/api/v1/feedback", json={"kind": "idea", "message": "Add a budgets page please"}).status_code == 502


def test_validation_and_rate_limit(client, monkeypatch):
    _fake_github(monkeypatch)
    assert client.post("/api/v1/feedback", json={"kind": "idea", "message": "short"}).status_code == 422
    for _ in range(5):
        assert client.post("/api/v1/feedback", json={"kind": "question", "message": "How do I add a loan?"}).status_code == 201
    assert client.post("/api/v1/feedback", json={"kind": "question", "message": "How do I add a loan?"}).status_code == 429
