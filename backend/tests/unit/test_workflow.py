"""Workflow layer tests (matrix row C6) — platform-agnostic.

Three layers, all driven through the real objects:
  1. ``N8nWorkflowProvider`` against a throwaway stdlib HTTP server, so the
     bridge's wire format (paths, headers, JSON bodies, error mapping) is
     verified without needing Docker or an n8n instance.
  2. The ``workflow.*`` tools: default-deny webhook allowlist, graceful
     "unavailable" when no provider is configured, and audit behaviour via the
     agent loop.
  3. The ``/api/workflow`` endpoints: 501 when unconfigured, 200 when
     configured, 502 when the engine is unreachable.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api import FakeAdapter, auth, make_client, token

from app.core.policies import PolicyDenied
from app.core.store import Store
from app.main import create_app
from app.orchestration.agent import Agent
from app.providers.base import LlmResult, ToolCall
from app.providers.mock import ScriptedLlmProvider
from app.tools.registry import ToolContext, build_tools
from app.workflows.base import WorkflowProvider, WorkflowUnavailable
from app.workflows.local import LocalSchedulerWorkflowProvider
from app.workflows.n8n import N8nWorkflowProvider

# --- Fake engine (in-process) ----------------------------------------------


class FakeWorkflowProvider(WorkflowProvider):
    """Deterministic in-process engine used for tool/API tests."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.runs: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> dict[str, Any]:
        if self.fail:
            raise WorkflowUnavailable("engine down")
        return {"status": "ok"}

    def list_workflows(self) -> list[dict[str, Any]]:
        if self.fail:
            raise WorkflowUnavailable("engine down")
        return [{"id": "wf-1", "name": "Daily report", "active": True}]

    def run_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise WorkflowUnavailable("engine down")
        self.runs.append((workflow_id, payload))
        return {"started": True, "webhook": workflow_id}


# --- N8n provider wire format (real local HTTP server) ----------------------


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Any  # set by the test; holds routes + captured requests

    def _dispatch(self) -> None:
        route = (self.command, self.path.split("?")[0])
        handler = self.server.routes.get(route)
        self.server.requests.append((self.command, self.path, dict(self.headers)))
        if handler is None:
            self.send_error(404)
            return
        status, body, ctype = handler  # routes are (status, body, content-type) tuples
        payload = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.server.bodies.append(self.rfile.read(length))
        self._dispatch()

    def log_message(self, *args: Any) -> None:  # silence test output
        pass


@pytest.fixture()
def n8n_server():
    """A throwaway local HTTP server speaking just enough of the n8n API."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.routes = {
        ("GET", "/healthz"): (200, {"status": "ok"}, "application/json"),
        ("GET", "/api/v1/workflows"): (
            200,
            {"data": [{"id": "wf-1", "name": "Daily report", "active": True}]},
            "application/json",
        ),
        ("POST", "/webhook/daily-report"): (
            200,
            {"message": "Workflow executed successfully"},
            "application/json",
        ),
        ("POST", "/webhook/failing"): (500, "boom", "text/plain"),
    }
    server.requests: list[tuple[str, str, dict]] = []
    server.bodies: list[bytes] = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def make_n8n(server: Any, api_key: str = "secret") -> N8nWorkflowProvider:
    return N8nWorkflowProvider(base_url=f"http://127.0.0.1:{server.server_port}", api_key=api_key)


def _header(headers: dict[str, str], name: str) -> str:
    """HTTP header names are case-insensitive (RFC 9110); look up case-blindly."""
    return next(v for k, v in headers.items() if k.lower() == name.lower())


def test_n8n_health(n8n_server):
    assert make_n8n(n8n_server).health() == {"status": "ok"}


def test_n8n_list_workflows(n8n_server):
    rows = make_n8n(n8n_server).list_workflows()
    assert rows == [{"id": "wf-1", "name": "Daily report", "active": True}]
    method, path, headers = n8n_server.requests[0]
    assert (method, path) == ("GET", "/api/v1/workflows")
    assert _header(headers, "X-N8N-API-KEY") == "secret"


def test_n8n_run_workflow_posts_json_to_webhook(n8n_server):
    provider = make_n8n(n8n_server)
    result = provider.run_workflow("daily-report", {"date": "2026-10-09"})
    assert result == {"message": "Workflow executed successfully"}
    method, path, _ = n8n_server.requests[0]
    assert (method, path) == ("POST", "/webhook/daily-report")
    assert json.loads(n8n_server.bodies[0]) == {"date": "2026-10-09"}


def test_n8n_http_error_becomes_workflow_unavailable(n8n_server):
    provider = make_n8n(n8n_server)
    with pytest.raises(WorkflowUnavailable, match="HTTP 500"):
        provider.run_workflow("failing", {})


def test_n8n_connection_refused_becomes_workflow_unavailable():
    provider = N8nWorkflowProvider(base_url="http://127.0.0.1:1")  # port 1: nothing listens
    with pytest.raises(WorkflowUnavailable, match="cannot reach n8n"):
        provider.health()


def test_n8n_no_api_key_omits_header(n8n_server):
    provider = N8nWorkflowProvider(base_url=f"http://127.0.0.1:{n8n_server.server_port}")
    provider.list_workflows()
    assert "X-N8N-API-KEY" not in n8n_server.requests[0][2]


# --- Tools ---------------------------------------------------------------


def _ctx(store: Store, *, workflow=None, webhooks=()) -> ToolContext:
    return ToolContext(
        adapter=FakeAdapter(),
        store=store,
        allowlist_commands=frozenset({"echo"}),
        allowlist_apps=frozenset(),
        workflow=workflow,
        allowlist_webhooks=frozenset(webhooks),
    )


def _tool(ctx: ToolContext, name: str):
    return {t.name: t for t in build_tools(ctx)}[name]


def test_workflow_run_denied_when_webhook_not_allowlisted(tmp_path):
    ctx = _ctx(Store(tmp_path / "a.db"), workflow=FakeWorkflowProvider(), webhooks=())
    spec = _tool(ctx, "workflow.run")
    with pytest.raises(PolicyDenied, match="not allowlisted"):
        spec.policy({"webhook": "daily-report"})


def test_workflow_run_allowed_when_allowlisted(tmp_path):
    provider = FakeWorkflowProvider()
    ctx = _ctx(Store(tmp_path / "b.db"), workflow=provider, webhooks=("daily-report",))
    spec = _tool(ctx, "workflow.run")
    spec.policy({"webhook": "daily-report"})  # must not raise
    out = spec.run(ctx, {"webhook": "daily-report", "input": {"x": 1}})
    assert provider.runs == [("daily-report", {"x": 1})]
    assert "started" in out


def test_workflow_tools_unavailable_when_not_configured(tmp_path):
    ctx = _ctx(Store(tmp_path / "c.db"), workflow=None)
    out = _tool(ctx, "workflow.run").run(ctx, {"webhook": "x"})
    assert "not configured" in out
    assert "JARVIS_N8N_BASE_URL" in out


def test_workflow_tools_report_unreachable_engine(tmp_path):
    ctx = _ctx(Store(tmp_path / "d.db"), workflow=FakeWorkflowProvider(fail=True))
    out = _tool(ctx, "workflow.list").run(ctx, {})
    assert "Workflow unavailable" in out


def test_agent_runs_allowlisted_workflow_and_audits(tmp_path):
    store = Store(tmp_path / "e.db")
    provider = FakeWorkflowProvider()
    ctx = _ctx(store, workflow=provider, webhooks=("daily-report",))
    agent = Agent(
        llm=ScriptedLlmProvider(
            [
                LlmResult(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="workflow.run",
                            arguments='{"webhook": "daily-report", "input": {"date": "today"}}',
                        )
                    ]
                ),
                LlmResult(text="started"),
            ]
        ),
        ctx=ctx,
    )
    result = agent.run("s1", "run the daily report")
    assert result.text == "started"
    assert provider.runs == [("daily-report", {"date": "today"})]
    audit = store.list_audit()
    assert any(
        r["capability"] == "workflow.run" and r["decision"] == "allow" and r["outcome"] == "ok"
        for r in audit
    )


def test_agent_denies_non_allowlisted_workflow_and_audits(tmp_path):
    store = Store(tmp_path / "f.db")
    ctx = _ctx(store, workflow=FakeWorkflowProvider(), webhooks=())
    agent = Agent(
        llm=ScriptedLlmProvider(
            [
                LlmResult(
                    tool_calls=[
                        ToolCall(id="c1", name="workflow.run", arguments='{"webhook": "evil"}')
                    ]
                ),
                LlmResult(text="ok"),
            ]
        ),
        ctx=ctx,
    )
    result = agent.run("s1", "run evil")
    tool_outcome = next(
        (m["content"] for m in reversed(result.messages) if m["role"] == "tool"), ""
    )
    assert "Denied by policy" in tool_outcome
    audit = store.list_audit()
    assert any(r["capability"] == "workflow.run" and r["decision"] == "deny" for r in audit)


# --- API ------------------------------------------------------------------


def test_workflow_api_501_when_unconfigured(tmp_path):
    client = make_client(tmp_path)  # no n8n settings → provider None
    tok = token(client)
    resp = client.get("/api/workflow/health", headers=auth(tok))
    assert resp.status_code == 501
    assert resp.json()["detail"]["capability"] == "workflow"


def test_workflow_api_requires_token(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/workflow/health").status_code == 401


def test_workflow_api_health_and_list_ok(tmp_path):
    client = make_client(tmp_path, workflow=FakeWorkflowProvider())
    tok = token(client)
    assert client.get("/api/workflow/health", headers=auth(tok)).json() == {"status": "ok"}
    body = client.get("/api/workflow/list", headers=auth(tok)).json()
    assert body["workflows"][0]["name"] == "Daily report"


def test_workflow_api_run_on_demand(tmp_path):
    client = make_client(tmp_path, workflow=FakeWorkflowProvider())
    tok = token(client)
    resp = client.post(
        "/api/workflow/wf-1/run",
        json={"payload": {"subject": "standup"}},
        headers=auth(tok),
    )
    assert resp.status_code == 200
    assert resp.json() == {"started": True, "webhook": "wf-1"}


def test_workflow_api_run_unknown_workflow_404(tmp_path):
    """Local scheduler: unknown workflow id → 404, mirroring the n8n bridge."""
    import app.main as main_mod

    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "wf.json").write_text(
        json.dumps(
            {
                "id": "wf",
                "name": "Wf",
                "schedule": {"type": "interval", "seconds": 3600},
                "steps": [{"tool": "memory.store", "args": {"fact": "x"}}],
            }
        ),
        encoding="utf-8",
    )
    settings = main_mod.get_settings().model_copy(update={"workflows_dir": str(wf_dir)})
    app = create_app(settings=settings, store=Store(tmp_path / "r.db"), adapter=FakeAdapter())
    provider = app.dependency_overrides[main_mod.get_workflow_dep]()
    try:
        client = TestClient(app)
        tok = token(client)
        assert client.post(
            "/api/workflow/nope/run", json={}, headers=auth(tok)
        ).status_code == 404
    finally:
        provider.stop()


def test_workflow_api_502_when_engine_down(tmp_path):
    client = make_client(tmp_path, workflow=FakeWorkflowProvider(fail=True))
    tok = token(client)
    resp = client.get("/api/workflow/health", headers=auth(tok))
    assert resp.status_code == 502
    assert resp.json()["detail"]["reason"] == "engine down"


def test_workflow_built_from_settings(tmp_path):
    """create_app constructs the real n8n provider when configured."""
    import app.main as main_mod

    app = create_app(
        settings=main_mod.get_settings().model_copy(
            update={"n8n_base_url": "http://127.0.0.1:5678", "n8n_api_key": "k"},
        ),
        store=Store(tmp_path / "g.db"),
        adapter=FakeAdapter(),
    )
    assert isinstance(app.dependency_overrides[main_mod.get_workflow_dep](), N8nWorkflowProvider)


def test_create_app_wires_local_scheduler_and_executes_with_audit(tmp_path):
    """C6 local half end-to-end: build_workflow picks the in-process scheduler,
    create_app binds the agent executor + starts the thread, and running a
    workflow executes each step through the policy → audit path (actor
    "scheduler"), just like a chat-initiated tool call."""
    import app.main as main_mod

    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "daily-report.json").write_text(
        json.dumps(
            {
                "id": "daily-report",
                "name": "Daily report",
                "schedule": {"type": "interval", "seconds": 3600},
                "steps": [
                    {"tool": "memory.store", "args": {"fact": "report {{input.subject}}"}},
                    {"tool": "shell.run", "args": {"command": "echo {{input.subject}}"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = main_mod.get_settings().model_copy(
        update={
            "workflows_dir": str(wf_dir),
            "allowlist_commands": ("echo",),
        }
    )
    store = Store(tmp_path / "scheduler.db")
    app = create_app(
        settings=settings,
        store=store,
        adapter=FakeAdapter(),
        workflow=None,
    )
    try:
        provider = app.dependency_overrides[main_mod.get_workflow_dep]()
        assert isinstance(provider, LocalSchedulerWorkflowProvider)
        # create_app bound the agent executor and started the tick thread
        assert provider.health()["scheduler_thread"] is True

        result = provider.run_workflow("daily-report", {"subject": "standup"})
        assert result["workflow"] == "daily-report"
        assert result["steps"][0]["outcome"] == "stored"
        assert "ok" in result["steps"][1]["outcome"]

        audit = store.list_audit()
        memory_row = next(
            r for r in audit if r["capability"] == "memory.store"
        )
        assert memory_row["actor"] == "scheduler"
        assert "standup" in memory_row["target"]
        shell_row = next(r for r in audit if r["capability"] == "shell.run")
        assert shell_row["actor"] == "scheduler"
        assert shell_row["decision"] == "allow" and shell_row["outcome"] == "ok"
    finally:
        provider.stop()