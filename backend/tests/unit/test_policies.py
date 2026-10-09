"""Policy engine tests (matrix row C5)."""
from __future__ import annotations

import pytest

from app.core.policies import PolicyDenied, ShellPolicy


def test_default_deny():
    with pytest.raises(PolicyDenied):
        ShellPolicy().check("ls /")


def test_empty_command_denied():
    with pytest.raises(PolicyDenied):
        ShellPolicy(allowed_executables=frozenset({"ls"})).check("   ")


def test_allowlisted_executable_passes():
    ShellPolicy(allowed_executables=frozenset({"echo"})).check("echo hello")


def test_prefix_not_allowlisted():
    # "ech" is not "echo" — exact token match.
    with pytest.raises(PolicyDenied):
        ShellPolicy(allowed_executables=frozenset({"echo"})).check("ech hello")


def test_path_escaping_denied():
    with pytest.raises(PolicyDenied):
        ShellPolicy(allowed_executables=frozenset({"echo"})).check("./bin/evil")


def test_absolute_path_denied():
    with pytest.raises(PolicyDenied):
        ShellPolicy(allowed_executables=frozenset({"echo"})).check("/bin/rm -rf /")