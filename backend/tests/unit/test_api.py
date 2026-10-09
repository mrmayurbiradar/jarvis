"""API tests with a fake platform adapter (platform-agnostic)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.store import Store
from app.execution.platform.base import (
    PlatformAdapter,
    ShellResult,
    SystemInfo,
    UnsupportedCapability,
)
from app.main import create_app
from app.providers.base import LlmProvider, LlmResult, ToolCall
from app.providers.mock import ScriptedLlmProvider
from app.workflows.base import WorkflowProvider


class FakeAdapter(PlatformAdapter):
    platform = "fake"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"shell": True, "launch_application": False}

    def default_shell(self) -> str:
        return "sh"

    def launch_application(self, target: str, *, wait: bool = False) -> int:
        raise UnsupportedCapability("launch_application", "fake platform has no app launching")

    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        return ShellResult(command=command, exit_code=0, stdout="ok", stderr="")

    def system_info(self) -> SystemInfo:
        return SystemInfo(
            os_name="fake",
            os_version="1.0",
            architecture="x86_64",
            hostname="fake-host",
            cpu_count=1,
            memory_total_bytes=1024,
            platform=self.platform,
        )


class FailingShellAdapter(FakeAdapter):
    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        raise UnsupportedCapability("shell", "shell not available")


def make_client(
    tmp_path,
    adapter: PlatformAdapter | None = None,
    workflow: WorkflowProvider | None = None,
    llm: LlmProvider | None = None,
    **settings_kwargs,
) -> TestClient:
    settings = Settings(**settings_kwargs)
    app = create_app(
        settings=settings,
        adapter=adapter or FakeAdapter(),
        store=Store(tmp_path / "test.db"),
        workflow=workflow,
        llm=llm,
    )
    return TestClient(app)


def token(client: TestClient) -> str:
    code = client.post("/api/pair/request", json={"display_name": "t"}).json()["code"]
    return client.post("/api/pair/confirm", json={"code": code}).json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_healthz_reports_deployment_mode(tmp_path):
    client = make_client(tmp_path, deployment_mode="hybrid")
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "deployment_mode": "hybrid"}


def test_cors_preflight_allows_browser_client(tmp_path):
    """The web/desktop clients live on a different origin; preflight must pass."""
    client = make_client(tmp_path)
    resp = client.options(
        "/api/capabilities",
        headers={
            "Origin": "http://127.0.0.1:1420",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


def test_capabilities_reports_fake_platform(tmp_path):
    client = make_client(tmp_path)
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "fake"
    assert body["capabilities"]["launch_application"] is False


def test_shell_denied_when_allowlist_empty(tmp_path):
    client = make_client(tmp_path)
    tok = token(client)
    resp = client.post(
        "/api/worker/shell", json={"command": "echo hello"}, headers=auth(tok)
    )
    assert resp.status_code == 403


def test_shell_denied_for_non_allowlisted_command(tmp_path):
    client = make_client(tmp_path, allowlist_commands=("echo",))
    tok = token(client)
    resp = client.post(
        "/api/worker/shell", json={"command": "rm -rf /"}, headers=auth(tok)
    )
    assert resp.status_code == 403


def test_shell_allowed_when_allowlisted(tmp_path):
    client = make_client(tmp_path, allowlist_commands=("echo",))
    tok = token(client)
    resp = client.post(
        "/api/worker/shell", json={"command": "echo hello"}, headers=auth(tok)
    )
    assert resp.status_code == 200
    assert resp.json()["stdout"] == "ok"


def test_unsupported_capability_returns_501(tmp_path):
    client = make_client(
        tmp_path, adapter=FailingShellAdapter(), allowlist_commands=("echo",)
    )
    tok = token(client)
    resp = client.post(
        "/api/worker/shell", json={"command": "echo hello"}, headers=auth(tok)
    )
    assert resp.status_code == 501
    body = resp.json()["detail"]
    assert body["capability"] == "shell"


def _gated_client(tmp_path):
    """Client whose LLM calls shell.run once, then replies — with approval on."""
    scripted = ScriptedLlmProvider(
        [
            LlmResult(
                tool_calls=[
                    ToolCall(id="c1", name="shell.run", arguments='{"command": "echo hi"}')
                ]
            ),
            LlmResult(text="done"),
        ]
    )
    client = make_client(
        tmp_path,
        llm=scripted,
        require_approval=True,
        allowlist_commands=("echo",),
    )
    return client, token(client)


def test_approval_gate_queues_pending_record(tmp_path):
    """A gated tool call does not run; it lands in the pending approval queue."""
    client, tok = _gated_client(tmp_path)
    resp = client.post("/api/chat", json={"message": "run echo hi"}, headers=auth(tok))
    assert resp.status_code == 200
    assert resp.json()["text"] == "done"  # LLM fell back after the block

    pending = client.get("/api/approvals/pending", headers=auth(tok))
    assert pending.status_code == 200
    body = pending.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["capability"] == "shell.run"
    assert entry["status"] == "pending"
    assert entry["target"] == {"command": "echo hi"}

    # The blocked attempt is audited for traceability.
    audit = client.get("/api/audit", headers=auth(tok)).json()
    assert any(e["outcome"] == "blocked" for e in audit)


def test_approval_approve_executes_and_audits(tmp_path):
    """Approve re-runs the action through gates 1-2 and records allow/ok."""
    client, tok = _gated_client(tmp_path)
    client.post("/api/chat", json={"message": "run echo hi"}, headers=auth(tok))
    approval_id = client.get("/api/approvals/pending", headers=auth(tok)).json()[0]["id"]

    resp = client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": "approve"},
        headers=auth(tok),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert "exit_code=0" in resp.json()["result"]

    # Queue drained, execution audited.
    assert client.get("/api/approvals/pending", headers=auth(tok)).json() == []
    audit = client.get("/api/audit", headers=auth(tok)).json()
    assert any(
        e["capability"] == "shell.run" and e["decision"] == "allow" and e["outcome"] == "ok"
        for e in audit
    )


def test_approval_deny_audits_rejected(tmp_path):
    client, tok = _gated_client(tmp_path)
    client.post("/api/chat", json={"message": "run echo hi"}, headers=auth(tok))
    approval_id = client.get("/api/approvals/pending", headers=auth(tok)).json()[0]["id"]

    resp = client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": "deny"},
        headers=auth(tok),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "denied"
    assert client.get("/api/approvals/pending", headers=auth(tok)).json() == []
    audit = client.get("/api/audit", headers=auth(tok)).json()
    assert any(
        e["decision"] == "deny" and e["outcome"] == "rejected"
        and "denied approval" in e["reason"]
        for e in audit
    )


def test_approval_respond_unknown_404(tmp_path):
    client, tok = _gated_client(tmp_path)
    resp = client.post(
        "/api/approvals/does-not-exist/respond",
        json={"decision": "approve"},
        headers=auth(tok),
    )
    assert resp.status_code == 404


def test_approval_respond_twice_409(tmp_path):
    client, tok = _gated_client(tmp_path)
    client.post("/api/chat", json={"message": "run echo hi"}, headers=auth(tok))
    approval_id = client.get("/api/approvals/pending", headers=auth(tok)).json()[0]["id"]

    first = client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": "approve"},
        headers=auth(tok),
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/approvals/{approval_id}/respond",
        json={"decision": "deny"},
        headers=auth(tok),
    )
    assert second.status_code == 409


def test_approval_bad_decision_422(tmp_path):
    client, tok = _gated_client(tmp_path)
    resp = client.post(
        "/api/approvals/none/respond",
        json={"decision": "maybe"},
        headers=auth(tok),
    )
    assert resp.status_code == 422


def test_approval_endpoints_require_worker_token(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/approvals/pending").status_code == 401
    assert (
        client.post("/api/approvals/x/respond", json={"decision": "approve"}).status_code
        == 401
    )