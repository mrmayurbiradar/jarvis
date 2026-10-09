"""Default-deny policy engine for computer operations (matrix row C5, ADR-0005).

Every operation passes through a policy before execution. This module
implements the shell-command allowlist; the same shape extends to
filesystem paths and application launching in later iterations.
"""
from __future__ import annotations

from dataclasses import dataclass


class PolicyDenied(Exception):
    """The operation is not permitted by policy."""


@dataclass(frozen=True)
class ShellPolicy:
    """Allowlist for approved shell commands.

    A command is approved iff its first token (the executable) is in the
    allowlist. Matching is exact on the token — `./bin/evil`, `/bin/ls`,
    or `ech o` are all denied even if a prefix looks close. The default
    allowlist is empty: deny by default.
    """

    allowed_executables: frozenset[str] = frozenset()

    def check(self, command: str) -> None:
        stripped = command.strip()
        if not stripped:
            raise PolicyDenied("empty command")
        token = stripped.split(maxsplit=1)[0]
        if token not in self.allowed_executables:
            raise PolicyDenied(f"executable not allowlisted: {token!r}")