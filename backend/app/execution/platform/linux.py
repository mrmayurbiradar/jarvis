"""Linux implementation of the OS abstraction (ADR-0003).

Uses `xdg-open` (or `gio open` as a fallback) for application launching —
but never substitutes a *dangerous* approximation when both are missing:
it raises `UnsupportedCapability` instead.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess

import psutil

from .base import PlatformAdapter, ShellResult, SystemInfo, UnsupportedCapability

# $SHELL is honored only if it resolves to a real, known shell. Never hardcoded
# to a literal path — resolved from PATH or the environment.
_SHELLS = ("bash", "zsh", "sh")


class LinuxAdapter(PlatformAdapter):
    platform = "linux"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "launch_application": shutil.which("xdg-open") is not None
            or shutil.which("gio") is not None,
            "shell": True,
            "system_info": True,
        }

    def default_shell(self) -> str:
        env_shell = os.environ.get("SHELL")
        if env_shell and os.path.basename(env_shell) in _SHELLS and shutil.which(env_shell):
            return env_shell
        for name in _SHELLS:
            resolved = shutil.which(name)
            if resolved:
                return resolved
        raise UnsupportedCapability("shell", "no usable shell found on PATH")

    def launch_application(self, target: str, *, wait: bool = False) -> int:
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if not opener:
            raise UnsupportedCapability(
                "launch_application", "neither xdg-open nor gio is available"
            )
        args = [opener, target]
        if opener.endswith("gio"):
            args = [opener, "open", target]
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc.wait() if wait else proc.pid

    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        shell = self.default_shell()
        try:
            proc = subprocess.run(
                [shell, "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ShellResult(command=command, exit_code=-1, stdout="", stderr="timed out")
        return ShellResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def system_info(self) -> SystemInfo:
        mem = psutil.virtual_memory()
        return SystemInfo(
            os_name="linux",
            os_version=platform.release(),
            architecture=platform.machine(),
            hostname=platform.node(),
            cpu_count=psutil.cpu_count(logical=True) or 0,
            memory_total_bytes=mem.total,
            platform=self.platform,
        )