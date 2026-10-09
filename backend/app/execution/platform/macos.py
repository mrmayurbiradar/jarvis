"""macOS implementation of the OS abstraction (ADR-0003).

Uses `open` (LaunchServices) for application launching. Wait mode blocks
on the launched process; otherwise returns its PID.
"""
from __future__ import annotations

import platform
import shutil
import subprocess

import psutil

from .base import PlatformAdapter, ShellResult, SystemInfo, UnsupportedCapability


class MacOSAdapter(PlatformAdapter):
    platform = "macos"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "launch_application": shutil.which("open") is not None,
            "shell": True,
            "system_info": True,
        }

    def default_shell(self) -> str:
        for name in ("zsh", "bash", "sh"):
            resolved = shutil.which(name)
            if resolved:
                return resolved
        raise UnsupportedCapability("shell", "no usable shell found on PATH")

    def launch_application(self, target: str, *, wait: bool = False) -> int:
        opener = shutil.which("open")
        if not opener:
            raise UnsupportedCapability("launch_application", "`open` is not available")
        proc = subprocess.Popen([opener, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            os_name="macos",
            os_version=platform.mac_ver()[0],
            architecture=platform.machine(),
            hostname=platform.node(),
            cpu_count=psutil.cpu_count(logical=True) or 0,
            memory_total_bytes=mem.total,
            platform=self.platform,
        )