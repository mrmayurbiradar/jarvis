"""Windows implementation of the OS abstraction (ADR-0003).

Uses `os.startfile` (ShellExecute semantics) for application launching;
wait mode is unsupported there and raises `UnsupportedCapability` rather
than faking a PID.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess

import psutil

from .base import PlatformAdapter, ShellResult, SystemInfo, UnsupportedCapability


class WindowsAdapter(PlatformAdapter):
    platform = "windows"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "launch_application": True,  # os.startfile always available
            "shell": True,
            "system_info": True,
        }

    def default_shell(self) -> str:
        # Prefer PowerShell; resolve via PATH (never a hardcoded path).
        for name in ("powershell", "pwsh", "cmd"):
            resolved = shutil.which(name)
            if resolved:
                return resolved
        raise UnsupportedCapability("shell", "no shell found on PATH")

    def launch_application(self, target: str, *, wait: bool = False) -> int:
        if wait:
            raise UnsupportedCapability(
                "launch_application", "wait mode is unsupported on Windows"
            )
        # os.startfile uses the OS default handler; it returns no PID.
        os.startfile(target)
        return 0

    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        shell = self.default_shell()
        try:
            proc = subprocess.run(
                [shell, "-NoProfile", "-Command", command] if "power" in os.path.basename(shell)
                else [shell, "/c", command],
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
            os_name="windows",
            os_version=platform.version(),
            architecture=platform.machine(),
            hostname=platform.node(),
            cpu_count=psutil.cpu_count(logical=True) or 0,
            memory_total_bytes=mem.total,
            platform=self.platform,
        )