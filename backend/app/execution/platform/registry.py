"""Per-platform implementations and runtime selection (ADR-0003).

Selection is by runtime OS at import time; tests inject fakes or select
an explicit platform via `adapter_for_platform(...)`.
"""
from __future__ import annotations

import sys

from .base import PlatformAdapter, UnsupportedCapability


def adapter_for_platform(platform: str | None = None) -> PlatformAdapter:
    """Return a configured adapter for `platform` (default: current OS)."""
    key = (platform or detect_platform()).lower()
    if key == "macos":
        from .macos import MacOSAdapter

        return MacOSAdapter()
    if key in ("windows", "win32", "win"):
        from .windows import WindowsAdapter

        return WindowsAdapter()
    if key == "linux":
        from .linux import LinuxAdapter

        return LinuxAdapter()
    raise UnsupportedCapability("platform", f"unsupported platform: {key!r}")


def detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform