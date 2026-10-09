"""FastAPI application factory.

The core backend is platform-independent: the platform adapter (ADR-0003),
the durable store, and the agent are injected as dependencies, so tests
substitute fakes and the same app runs on macOS, Windows and Linux.

Security gates (ADR-0005), in order, on any computer operation:
  1. pairing / worker token   → auth.require_worker_token
  2. default-deny policy      → policies.ShellPolicy
  3. approval (opt-in)        → settings.require_approval (client UI later)
Every operation is written to the append-only audit log.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.api import audit, auth, chat
from app.api import workflow as workflow_api
from app.config import Settings, get_settings
from app.core.auth import require_worker_token
from app.core.deps import (
    get_adapter_dep,
    get_agent_dep,
    get_settings_dep,
    get_store_dep,
    get_workflow_dep,
)
from app.core.policies import PolicyDenied, ShellPolicy
from app.core.store import Store
from app.execution.platform.base import PlatformAdapter, ShellResult, UnsupportedCapability
from app.orchestration.agent import Agent
from app.providers import build_llm
from app.tools.registry import ToolContext
from app.workflows import build_workflow
from app.workflows.base import WorkflowProvider


class ShellRequest(BaseModel):
    command: str
    timeout: float | None = 30.0


def create_app(
    settings: Settings | None = None,
    adapter: PlatformAdapter | None = None,
    store: Store | None = None,
    workflow: WorkflowProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    adapter = adapter or get_adapter_dep()
    store = store or Store(settings.resolved_db_path)
    workflow = workflow if workflow is not None else build_workflow(settings)

    ctx = ToolContext(
        adapter=adapter,
        store=store,
        allowlist_commands=frozenset(settings.allowlist_commands),
        allowlist_apps=frozenset(settings.allowlist_apps),
        workflow=workflow,
        allowlist_webhooks=frozenset(settings.allowlist_webhooks),
    )
    agent = Agent(llm=build_llm(settings), ctx=ctx, require_approval=settings.require_approval)

    app = FastAPI(title="JARVIS core backend", version="0.1.0")

    # Inject the app-specific instances into the module-level dependencies.
    app.dependency_overrides.update(
        {
            get_settings_dep: lambda: settings,
            get_adapter_dep: lambda: adapter,
            get_store_dep: lambda: store,
            get_agent_dep: lambda: agent,
            get_workflow_dep: lambda: workflow,
        }
    )

    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(audit.router)
    app.include_router(workflow_api.router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "deployment_mode": settings.deployment_mode}

    @app.get("/api/capabilities")
    def capabilities(adapter: Annotated[PlatformAdapter, Depends(get_adapter_dep)]) -> dict:
        """Advertise exactly what is implemented and tested on this platform."""
        return {
            "platform": adapter.platform,
            "deployment_mode": settings.deployment_mode,
            "capabilities": adapter.capabilities,
        }

    @app.post("/api/worker/shell")
    def run_shell(
        body: ShellRequest,
        _: Annotated[str, Depends(require_worker_token)],
        adapter: Annotated[PlatformAdapter, Depends(get_adapter_dep)],
    ) -> ShellResult:
        # Gate 2 of ADR-0005: default-deny policy before anything executes.
        policy = ShellPolicy(allowed_executables=frozenset(settings.allowlist_commands))
        try:
            policy.check(body.command)
        except PolicyDenied as exc:
            store.append_audit(
                actor="worker",
                capability="shell.run",
                target=body.command,
                decision="deny",
                outcome="rejected",
                reason=str(exc),
            )
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            result = adapter.run_shell(body.command, timeout=body.timeout)
        except UnsupportedCapability as exc:
            store.append_audit(
                actor="worker",
                capability="shell.run",
                target=body.command,
                decision="allow",
                outcome="error",
                reason=f"unsupported: {exc.reason}",
            )
            raise HTTPException(
                status_code=501,
                detail={"capability": exc.capability, "reason": exc.reason},
            ) from exc
        store.append_audit(
            actor="worker",
            capability="shell.run",
            target=body.command,
            decision="allow",
            outcome="ok",
        )
        return result

    return app


app = create_app()