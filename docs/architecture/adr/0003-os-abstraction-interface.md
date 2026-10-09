# ADR-0003: OS abstraction interface (PlatformAdapter)

- **Status:** Accepted
- **Date:** 2026-10 (baseline decision)
- **Owner:** Execution layer (local worker), Client layer

## Context

The spec mandates: "Create a common interface for local computer operations,
with separate implementations for macOS, Windows and Linux." It must detect
platform capabilities at runtime, fail gracefully when an operation is
unsupported, and **never silently substitute a dangerous command for an
unavailable platform feature**.

There are two distinct owners of OS-specific behavior:

1. **Client shell** (Rust/Tauri) — mic, wake word, notifications, tray, autostart,
   clipboard, hotkeys. Implemented as Tauri plugins + commands (ADR-0001).
2. **Backend local worker** (Python) — app launching, file/dir ops, approved
   shell commands, process management, system info, worker notifications.

Both need the same *shape* of abstraction. This ADR specifies the shared contract.

## Contract

### Runtime capability detection

Every capability is registered in a **capability registry** at startup. The
worker/client exposes `GET /api/capabilities` (backend) / `capabilities()` IPC
(client) listing what is *actually* available on the running OS and desktop
session. The client UI must not offer actions that are not advertised.

### Graceful degradation

Every operation returns one of:

- `Ok(result)` — success
- `UnsupportedCapability(capability, reason)` — the OS/session lacks the feature.
  This is **not an error**; it is a typed, expected outcome that the UI surfaces
  ("Wake word unavailable on this system — manual trigger only").
- `Failure(code, message)` — the operation is supported but failed.

A platform implementation may omit an operation entirely (leaving the ABC's
default `raise UnsupportedCapability`), but must never return `Ok` for something
it did not do.

### No dangerous substitution (hard rule)

If a native feature is unavailable, the implementation must **not** substitute a
shell/command that merely approximates it. Examples of forbidden substitutions:

- Emulating "move/raise window" via process kill + relaunch.
- Emulating "wake word" via an unbounded CPU polling loop.
- Emulating "screen capture" on a Wayland session via `xwd` on a nested X server.

The correct response is `UnsupportedCapability` with a human-readable reason and,
where applicable, an alternative the platform *does* support.

### DI and adapters

- `PlatformAdapter` is an abstract base class; `macos.py`, `windows.py`,
  `linux.py` implement it.
- Selection is by runtime OS + configuration override (tests inject fakes).
- In FastAPI, the adapter is registered as a dependency (`Depends(adapter)`).
- Core code imports only `base.py`; it is unit-tested against fake adapters and
  therefore platform-agnostic.

### Paths, executables, users (portability)

- Home directory, usernames, and executable paths never appear as literals.
- Use `platformdirs`-style resolution + `pydantic-settings` config with env
  overrides (matrix row D1).
- The worker's shell is read from config (with a safe default per OS), never
  hardcoded as `/bin/zsh` etc.

## Shape (backend, illustrative)

```python
# backend/app/execution/platform/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass(frozen=True)
class UnsupportedCapability(Exception):
    capability: str
    reason: str

class PlatformAdapter(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Runtime capability probe, e.g. {"shell.allowlisted": True, ...}."""

    @abstractmethod
    def launch_application(self, target: str, *, wait: bool = False) -> int: ...

    @abstractmethod
    def filesystem(self) -> FilesystemOps: ...

    @abstractmethod
    def run_shell(self, command: str, *, allowlist: Allowlist) -> ShellResult: ...

    @abstractmethod
    def processes(self) -> ProcessesOps: ...

    @abstractmethod
    def system_info(self) -> SystemInfo: ...
```

The client shell follows the same shape as Tauri commands returning the same
typed result enum (`Ok | UnsupportedCapability | Failure`).

## Consequences

- **Core stays OS-independent**; all platform code is confined to
  `execution/platform/` and the Tauri capability layer.
- **Testing** is split: platform-agnostic unit tests (fake adapters) run on all
  three OSes; per-OS tests are marked `@pytest.mark.platform("darwin|win32|linux")`
  and run on the matching CI runner (matrix rows D3/D4).
- **Feature parity** is documented by the portability matrix, enforced by the
  `/api/capabilities` endpoint (matrix row D5).

## Links

- Portability matrix D1–D5 (cross-cutting portability requirements)
- ADR-0001 (client shell; Tauri plugin boundary)
- Repository layout `backend/app/execution/platform/`