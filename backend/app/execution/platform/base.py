"""OS abstraction common interface (ADR-0003).

Contract rules:

1. **Common interface** — one API, per-platform implementations.
2. **Runtime capability detection** — probe what is actually available.
3. **Graceful degradation** — a missing capability raises
   `UnsupportedCapability` (a typed, expected outcome), never a crash.
4. **No dangerous substitution** — never emulate a missing native feature
   with a shell/command that merely approximates it. Surface the
   `UnsupportedCapability` with a human-readable reason instead.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class UnsupportedCapability(Exception):
    """The platform does not provide the requested capability.

    This is an expected outcome, not an error: the caller surfaces it to
    the user ("Wake word unavailable on this system — manual trigger only")
    and must not fall back to a semantically different substitute.
    """

    def __init__(self, capability: str, reason: str) -> None:
        super().__init__(f"{capability}: {reason}")
        self.capability = capability
        self.reason = reason


@dataclass(frozen=True)
class ShellResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SystemInfo:
    os_name: str
    os_version: str
    architecture: str
    hostname: str
    cpu_count: int
    memory_total_bytes: int
    platform: str


class PlatformAdapter(ABC):
    """Common interface for local computer operations.

    Implementations: `macos.py`, `windows.py`, `linux.py`.
    """

    #: stable platform key, e.g. "macos", "windows", "linux"
    platform: str = "unknown"

    @property
    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Runtime capability probe, e.g. {"shell.allowlisted": True, ...}."""

    @abstractmethod
    def default_shell(self) -> str:
        """Config-independent default shell for this platform."""

    @abstractmethod
    def launch_application(self, target: str, *, wait: bool = False) -> int:
        """Open an app/URL/file with the OS default handler.

        Returns the PID of the launched process when `wait=False`, else
        blocks and returns the exit code.
        """

    @abstractmethod
    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        """Run an approved shell command."""

    @abstractmethod
    def system_info(self) -> SystemInfo:
        """Read basic system metrics (matrix row B5)."""