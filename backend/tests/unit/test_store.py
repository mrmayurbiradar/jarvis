"""Durable store tests: pairing, audit, memory, sessions, tasks."""
from __future__ import annotations

import pytest

from app.core.store import Store


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def test_pairing_flow_issues_valid_token(store):
    req = store.request_pairing("test-worker")
    assert req["code"] and req["pairing_id"]
    assert store.verify_worker_token("anything") is False
    token = store.confirm_pairing(req["code"])
    assert token
    assert store.verify_worker_token(token) is True


def test_pairing_wrong_code_denied(store):
    assert store.confirm_pairing("000000") is None


def test_pairing_expired_code_denied(tmp_path):
    store = Store(tmp_path / "test.db", ttl_seconds=0)
    req = store.request_pairing("x")
    assert store.confirm_pairing(req["code"]) is None


def test_revocation_invalidates_token(store):
    req = store.request_pairing("w")
    token = store.confirm_pairing(req["code"])
    assert store.revoke_worker(token) is True
    assert store.verify_worker_token(token) is False
    # double revoke is a no-op
    assert store.revoke_worker(token) is False


def test_audit_append_only_and_ordered(store):
    store.append_audit(actor="a", capability="shell.run", target="ls", decision="deny")
    store.append_audit(actor="a", capability="system.info", decision="allow", outcome="ok")
    rows = store.list_audit()
    assert len(rows) == 2
    assert rows[0]["capability"] == "system.info"  # newest first


def test_session_messages_roundtrip(store):
    assert store.get_session_messages("s1") == []
    store.append_session_messages("s1", [{"role": "user", "content": "hi"}])
    assert store.get_session_messages("s1") == [{"role": "user", "content": "hi"}]


def test_memory_save_and_recall(store):
    store.save_memory("s1", "user prefers dark mode")
    store.save_memory("s1", "project is JARVIS")
    hits = store.recall_memory("dark")
    assert len(hits) == 1
    assert hits[0]["fact"] == "user prefers dark mode"


def test_task_state_machine(store):
    task = store.create_task("test", {"n": 1})
    assert task["status"] == "queued"
    store.set_task_status(task["id"], "running")
    store.set_task_status(task["id"], "done")
    with pytest.raises(KeyError):
        store.set_task_status("missing", "done")