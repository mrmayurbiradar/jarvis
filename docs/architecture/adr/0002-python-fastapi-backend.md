# ADR-0002: Python + FastAPI for the core backend

- **Status:** Accepted
- **Date:** 2026-10 (baseline decision)
- **Owner:** Core backend, Execution layer, Provider layer

## Context

The core backend must be platform-independent, independently runnable and
testable, and must integrate AI providers (LLM, STT, TTS), tool orchestration
(MCP), and workflow systems (n8n). It runs in three deployment modes (local-only,
hybrid, remote) and must be testable on macOS, Windows and Linux from CI.

## Options considered

| | Python + FastAPI | Node.js (TypeScript) | Rust (axum) | Go |
|---|---|---|---|---|
| AI/provider ecosystem | Strong (many SDKs, python-first research stack) | Strong | Growing | Limited |
| Async IO | Excellent (`async`/`await`, `anyio`) | Native | Excellent | Excellent |
| Tooling (LSP, tests, packaging) | Mature (`uv`, pytest, pydantic) | Mature | Good | Good |
| Platform-independent runtime | CPython is everywhere; no OS APIs used in `core/` | Node everywhere | Native binaries per-OS | Native binaries per-OS |
| DI / testability | FastAPI DI + pytest fixtures | Inversify/manual | Manual | Manual |
| Independent of Docker | Yes (plain process) | Yes | Yes | Yes |

## Decision

Use **Python 3.12+ with FastAPI**, managed with `uv`, config via
`pydantic-settings`, ORM via SQLAlchemy (async), and tests via pytest.

Rationale:

1. **Spec-compliant:** "Python and FastAPI for the backend if suitable" — it is.
   The core business logic (auth, orchestration, memory, task state, policies,
   audit) needs no OS API at all; it runs unchanged on all three OSes.
2. **Independently runnable & testable:** `uv run fastapi dev` starts it with no
   containers; pytest covers core logic with `aiosqlite` in local mode.
3. **Provider layer fit:** Python has the broadest coverage for LLM/STT/TTS and
   data providers; the registry pattern in `providers/` keeps them replaceable.
4. **DI matches the adapter requirement** (spec: "dependency injection and
   adapters for platform-specific functionality") — FastAPI `Depends` + a
   `PlatformAdapter` ABC (ADR-0003).
5. **Async-first** suits WS streaming to clients and long agent loops.

### Consequences / mitigations

- **Performance** is adequate for orchestration/API duties; any hot paths (audio
  transcription serving) are isolated behind the provider interface and can be
  moved to a dedicated service later without rewiring the core.
- **Packaging:** single distributable via `uv build`/PyInstaller for the bundled
  backend process in Local mode (ADR-0004).
- **n8n** (workflow layer) stays a separate service (Node-based) accessed over
  HTTP — no language coupling.

## Alternatives rejected

- **Node/TypeScript**: fine, but Python's provider ecosystem is a better fit for
  the AI/automation provider layer and the spec explicitly offers Python.
- **Rust/Go**: stronger raw performance, weaker provider/tool ecosystem and
  slower iteration for agent orchestration code.

## Links

- ADR-0003 (OS abstraction interface, `backend/app/execution/platform/`)
- ADR-0004 (runtime & deployment modes)
- Repository layout `backend/`