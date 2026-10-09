"""Windows adapter smoke tests — run on the Windows CI runner."""
from __future__ import annotations

import sys

import pytest

from app.execution.platform.base import UnsupportedCapability
from app.execution.platform.registry import adapter_for_platform

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only adapter tests")


def test_windows_adapter_selected():
    assert adapter_for_platform("windows").platform == "windows"


def test_windows_system_info_shape():
    info = adapter_for_platform("windows").system_info()
    assert info.os_name == "windows"
    assert info.cpu_count >= 1


def test_windows_default_shell_is_real():
    import shutil

    shell = adapter_for_platform("windows").default_shell()
    assert shutil.which(shell)


def test_windows_launch_wait_mode_unsupported():
    with pytest.raises(UnsupportedCapability):
        adapter_for_platform("windows").launch_application("https://example.com", wait=True)