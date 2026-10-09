"""FastAPI application factory.

The core backend is platform-independent: the platform adapter (ADR-0003)
is injected as a dependency, so tests substitute fakes and the same app
runs on macOS, Windows and Linux.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.core.policies import PolicyDenied, ShellPolicy
from app.execution.platform.base import PlatformAdapter, ShellResult, UnsupportedCapability
from app.execution.platform.registry import adapter_for_platform


class ShellRequest(BaseModel):
    command: str
    timeout: float | None = 30.0


def get_adapter() -> PlatformAdapter:
    """Module-level dependency; `create_app` overrides it with the app's adapter.

    Module-level so it resolves under lazy (string) annotations — a closure
    defined inside `create_app` would not be reachable when FastAPI evaluates
    the `Depends(...)` metadata.
    """
    return adapter_for_platform()


def create_app(settings: Settings | None = None, adapter: PlatformAdapter | None = None) -> FastAPI:
    settings = settings or get_settings()
    adapter = adapter or adapter_for_platform()

    app = FastAPI(title="JARVIS core backend", version="0.1.0")
    app.dependency_overrides[get_adapter] = lambda: adapter

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "deployment_mode": settings.deployment_mode}

    @app.get("/api/capabilities")
    def capabilities() -> dict:
        """Advertise exactly what is implemented and tested on this platform."""
        return {
            "platform": adapter.platform,
            "deployment_mode": settings.deployment_mode,
            "capabilities": adapter.capabilities,
        }

    @app.post("/api/worker/shell")
    def run_shell(body: ShellRequest, adapter: Annotated[PlatformAdapter, Depends(get_adapter)]) -> ShellResult:
        # Gate 2 of ADR-0005: default-deny policy before anything executes.
        policy = ShellPolicy(allowed_executables=frozenset(settings.allowlist_commands))
        try:
            policy.check(body.command)
        except PolicyDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            return adapter.run_shell(body.command, timeout=body.timeout)
        except UnsupportedCapability as exc:
            raise HTTPException(
                status_code=501,
                detail={"capability": exc.capability, "reason": exc.reason},
            ) from exc

    return app


app = create_app()