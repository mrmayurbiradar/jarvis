"""API tests with a fake platform adapter (platform-agnostic)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.execution.platform.base import (
    PlatformAdapter,
    ShellResult,
    SystemInfo,
    UnsupportedCapability,
)
from app.main import create_app


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


def make_client(adapter: PlatformAdapter | None = None, **settings_kwargs) -> TestClient:
    settings = Settings(**settings_kwargs)
    return TestClient(create_app(settings=settings, adapter=adapter or FakeAdapter()))


def test_healthz_reports_deployment_mode():
    client = make_client(deployment_mode="hybrid")
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "deployment_mode": "hybrid"}


def test_capabilities_reports_fake_platform():
    client = make_client()
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "fake"
    assert body["capabilities"]["launch_application"] is False


def test_shell_denied_when_allowlist_empty():
    # Default-deny: nothing may run without an explicit allowlist.
    client = make_client()
    resp = client.post("/api/worker/shell", json={"command": "echo hello"})
    assert resp.status_code == 403


def test_shell_denied_for_non_allowlisted_command():
    client = make_client(allowlist_commands=("echo",))
    resp = client.post("/api/worker/shell", json={"command": "rm -rf /"})
    assert resp.status_code == 403


def test_shell_allowed_when_allowlisted():
    client = make_client(allowlist_commands=("echo",))
    resp = client.post("/api/worker/shell", json={"command": "echo hello"})
    assert resp.status_code == 200
    assert resp.json()["stdout"] == "ok"


def test_unsupported_capability_returns_501():
    client = make_client(adapter=FailingShellAdapter(), allowlist_commands=("echo",))
    resp = client.post("/api/worker/shell", json={"command": "echo hello"})
    assert resp.status_code == 501
    body = resp.json()["detail"]
    assert body["capability"] == "shell"