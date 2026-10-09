"""Pairing + auth-gate tests (ADR-0005)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.store import Store
from app.main import create_app


def _client(tmp_path) -> tuple[TestClient, Store]:
    store = Store(tmp_path / "test.db")
    app = create_app(settings=Settings(), store=store)
    return TestClient(app), store


def _paired_token(client: TestClient) -> str:
    code = client.post("/api/pair/request", json={"display_name": "t"}).json()["code"]
    return client.post("/api/pair/confirm", json={"code": code}).json()["token"]


def test_pairing_roundtrip(tmp_path):
    client, _ = _client(tmp_path)
    req = client.post("/api/pair/request", json={"display_name": "test-worker"})
    assert req.status_code == 200
    assert len(req.json()["code"]) == 6
    token = _paired_token(client)
    assert token


def test_confirm_rejects_bad_code(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/pair/confirm", json={"code": "000000"})
    assert resp.status_code == 404


def test_audit_requires_token(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/audit").status_code == 401
    token = _paired_token(client)
    resp = client.get("/api/audit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_shell_requires_token(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post(
        "/api/worker/shell", json={"command": "echo hi"}
    )
    assert resp.status_code == 401


def test_revoked_token_is_rejected(tmp_path):
    client, store = _client(tmp_path)
    token = _paired_token(client)
    store.revoke_worker(token)
    resp = client.post(
        "/api/worker/shell",
        json={"command": "echo hi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401