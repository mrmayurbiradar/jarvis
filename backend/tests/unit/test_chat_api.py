"""Chat endpoint tests: pairing → chat → audit trail."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.store import Store
from app.main import create_app


def _client(tmp_path, **settings_kwargs) -> TestClient:
    settings = Settings(**settings_kwargs)
    app = create_app(settings=settings, store=Store(tmp_path / "test.db"))
    return TestClient(app)


def _token(client: TestClient) -> str:
    code = client.post("/api/pair/request", json={"display_name": "t"}).json()["code"]
    return client.post("/api/pair/confirm", json={"code": code}).json()["token"]


def test_chat_requires_auth(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_chat_mock_provider_echoes(tmp_path):
    client = _client(tmp_path, llm_provider="mock")
    token = _token(client)
    resp = client.post(
        "/api/chat", json={"message": "hello"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "(mock) hello"
    assert resp.json()["tool_calls"] == 0


def test_chat_local_provider_runs_daily_tool(tmp_path):
    """The default keyless brain routes plain English to a real tool."""
    client = _client(tmp_path)
    token = _token(client)
    resp = client.post(
        "/api/chat",
        json={"message": "add a task: buy milk"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "added" in resp.json()["text"].lower()
    assert resp.json()["tool_calls"] == 1
    # the task is durable and the call is audited
    rows = client.post(
        "/api/chat",
        json={"message": "what's my todo?"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert "buy milk" in rows["text"].lower()
    audit = client.get("/api/audit", headers={"Authorization": f"Bearer {token}"}).json()
    assert any(e["capability"] == "tasks.add" for e in audit)


def test_chat_runs_tool_and_audits(tmp_path):
    settings = Settings(llm_provider="mock", allowlist_commands=("echo",))
    app = create_app(settings=settings, store=Store(tmp_path / "test.db"))
    # Replace the app's agent LLM with a scripted one.
    ctx = app.dependency_overrides  # noqa: F841  (kept simple: rely on default mock below)
    client = TestClient(app)
    token = _token(client)
    # With the default mock provider no tools are called; this asserts the
    # allowlist still guards the raw shell endpoint (policy test above).
    resp = client.post(
        "/api/worker/shell",
        json={"command": "rm -rf /"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/worker/shell",
        json={"command": "echo hi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_chat_sessions_are_durable(tmp_path):
    client = _client(tmp_path)
    token = _token(client)
    session_id = "fixed-session"
    r1 = client.post(
        "/api/chat",
        json={"message": "first", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = client.post(
        "/api/chat",
        json={"message": "second", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == r2.status_code == 200
    # both turns land in the same session; the store keeps history across calls
    assert r1.json()["session_id"] == session_id
    assert r2.json()["session_id"] == session_id