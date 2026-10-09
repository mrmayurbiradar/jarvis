"""Linux adapter smoke tests — run on the Linux CI runner."""
from __future__ import annotations

import sys

import pytest

from app.execution.platform.registry import adapter_for_platform

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only adapter tests")


def test_linux_adapter_selected():
    assert adapter_for_platform("linux").platform == "linux"


def test_linux_system_info_shape():
    info = adapter_for_platform("linux").system_info()
    assert info.os_name == "linux"
    assert info.cpu_count >= 1
    assert info.memory_total_bytes > 0


def test_linux_shell_echo():
    result = adapter_for_platform("linux").run_shell("echo jarvis", timeout=10)
    assert result.exit_code == 0
    assert result.stdout.strip() == "jarvis"


def test_linux_default_shell_is_real():
    import shutil

    shell = adapter_for_platform("linux").default_shell()
    assert shutil.which(shell)