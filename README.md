# JARVIS

Cross-platform AI automation platform. macOS is the initial development and
testing environment; Windows 10/11, Linux, and browser-based access are first-class
design targets from day one.

Cross-platform AI automation platform, designed from the start for macOS,
Windows 10/11, Linux, and browser-based access.

> **Read [`PROGRESS.md`](PROGRESS.md) first** — it's the living status/handoff
> doc: what's built, what's next, how to run and test.

## Status

| Milestone | State |
|-----------|-------|
| OS portability matrix | Done — `docs/architecture/02-portability-matrix.md` |
| Architecture overview | Done — `docs/architecture/01-overview.md` |
| ADRs (client, backend, OS abstraction, deployment, worker auth) | Done — `docs/architecture/adr/` |
| Repository layout | Done — `docs/architecture/03-repository-layout.md` |
| Backend scaffold (FastAPI + OS abstraction + policies) | Started — `backend/` |
| Backend tests on macOS/Windows/Linux | CI matrix — `.github/workflows/backend.yml` |
| Desktop client | Not started |

## Quick start (backend)

```bash
cd backend
uv sync --extra dev        # or: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
uv run pytest              # 16 passed (platform tests run on their OS in CI)
uv run fastapi dev app/main.py   # http://localhost:8000
```

Endpoints: `GET /healthz`, `GET /api/capabilities` (advertises what the current
platform actually supports), `POST /api/worker/shell` (default-deny allowlist).

The backend is platform-independent: OS-specific code lives only in
`backend/app/execution/platform/` behind the `PlatformAdapter` interface
(ADR-0003) and is injected as a dependency.

## Document map

- [Architecture overview](docs/architecture/01-overview.md) — layers, deployment modes, runtime resolver, security posture.
- [OS portability matrix](docs/architecture/02-portability-matrix.md) — every platform-specific capability: implementation, dependencies, verification test, per-OS.
- [Repository layout](docs/architecture/03-repository-layout.md) — proposed monorepo structure.
- [ADR-0001: Tauri vs Electron](docs/architecture/adr/0001-tauri-vs-electron.md)
- [ADR-0002: Python + FastAPI backend](docs/architecture/adr/0002-python-fastapi-backend.md)
- [ADR-0003: OS abstraction interface](docs/architecture/adr/0003-os-abstraction-interface.md)
- [ADR-0004: Backend runtime & deployment modes](docs/architecture/adr/0004-backend-runtime-and-deployment-modes.md)
- [ADR-0005: Local worker pairing & authorization](docs/architecture/adr/0005-local-worker-pairing-and-authorization.md)

## Non-goals for the first release

- Full feature parity on Windows/Linux at launch — unsupported capabilities must be
  *detected at runtime and fail gracefully*, not silently substituted.
- Mobile clients (designed for, not shipped).
- Any promise of identical support for a capability until it is tested on the target OS.