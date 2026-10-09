"""macOS adapter smoke tests — run on the macOS CI runner."""
from __future__ import annotations

import sys

import pytest

from app.execution.platform.registry import adapter_for_platform

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only adapter tests")


def test_macos_adapter_selected():
    assert adapter_for_platform("macos").platform == "macos"


def test_macos_system_info_shape():
    info = adapter_for_platform("macos").system_info()
    assert info.os_name == "macos"
    assert info.cpu_count >= 1


def test_macos_default_shell_is_real():
    import shutil

    shell = adapter_for_platform("macos").default_shell()
    assert shutil.which(shell)


def test_macos_capabilities_probe():
    caps = adapter_for_platform("macos").capabilities
    assert set(caps) == {"launch_application", "shell", "system_info"}