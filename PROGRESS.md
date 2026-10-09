# JARVIS — Progress & Handoff

> Read this first in a fresh session. It summarizes what exists, what's next,
> and how to run/test everything.

**Last updated:** 2026-10-09 (session: initial scaffold + first push)

## 1. What the project is

Cross-platform AI automation platform ("JARVIS"): an AI assistant that operates
the user's computer (launch apps, run approved shell commands, files, etc.)
across macOS / Windows / Linux, from a desktop (Tauri) or browser client.

- Repo: `https://github.com/mrmayurbiradar/jarvis` (remote `origin`, branch `main`)
- Local clone: `/root/jarvis-repo`
- Stale copy (docs server only, ignore): `/root/jarvis`

## 2. Where things live

| Path | What it is |
|---|---|
| `docs/architecture/01-overview.md` | 6-layer architecture, deployment modes, security posture |
| `docs/architecture/02-portability-matrix.md` | **The spec deliverable**: every capability × OS × deps × verification test |
| `docs/architecture/03-repository-layout.md` | Monorepo layout (backend is the only populated dir) |
| `docs/architecture/adr/0001-0005` | Decisions: Tauri, FastAPI, OS abstraction, deployment, worker auth |
| `backend/` | FastAPI core backend — the only code so far |
| `backend/app/execution/platform/` | **OS abstraction** (ADR-0003): `base.py` + `macos/windows/linux.py` + `registry.py` |
| `backend/app/core/policies.py` | Default-deny shell allowlist (ADR-0005 gate 2) |
| `backend/app/config.py` | Env-driven settings, platformdirs paths, no hardcoded anything |
| `backend/tests/` | `unit/` (platform-agnostic, fake adapter) + `platform/` (per-OS, CI runners) |
| `.github/workflows/backend.yml` | CI: runs backend tests on macOS/Windows/Linux |
| `scripts/serve_docs.py` | Renders `.md` docs as styled HTML (needs `.venv` w/ markdown+pygments) |

## 3. Current state

**Design: DONE.** **Coding: ~5–10% (backend scaffold only).**

### Done (verified)
- Design docs + 5 ADRs + portability matrix (all committed).
- FastAPI app: `GET /healthz`, `GET /api/capabilities`, `POST /api/worker/shell`.
- `PlatformAdapter` ABC + macOS/Windows/Linux adapters; runtime detection;
  graceful `UnsupportedCapability`; no-dangerous-substitution rule.
- Default-deny shell policy — allowlisted commands only; empty allowlist = deny all.
- Tests: **16 passed, 8 skipped on Linux** (skips = macOS/Windows adapter tests
  that run on their CI runners). Lint clean (`ruff`).
- Pushed to GitHub (`0b8f63c`). CI matrix configured for 3 OSes.

### NOT done (designed only)
Auth/pairing (ADR-0005) · agent orchestration (LLM) · memory · task state ·
audit log · workflows (n8n) · MCP tools · Docker Compose · Tauri desktop client ·
web client.

## 4. Next steps (recommended order)

1. **Auth + local-worker pairing** (ADR-0005 core) — the security gate that
   makes the platform trustworthy. Device-code pairing, tokens, revocable keys.
2. **Agent orchestration with a real LLM provider** — agent loop + tool routing
   behind the `providers/` interface. Makes it feel like an assistant.
3. **Tauri desktop shell** — wraps the shared frontend, owns mic/wake-word/
   clipboard (matrix A1–A11).

Each slice should: implement → unit test (platform-agnostic) → update this file.

## 5. How to run / test

```bash
cd /root/jarvis-repo/backend
.venv/bin/python -m pytest              # 16 pass on Linux (venv already built)
# or via uv:  uv sync --extra dev && uv run pytest

# Run the server (allowlist needed for shell to return 200):
JARVIS_ALLOWLIST_COMMANDS='["echo"]' .venv/bin/uvicorn app.main:app --port 8010
# Interactive API docs: http://127.0.0.1:8010/docs
```

Known gotcha (documented for posterity): with `from __future__ import
annotations`, a `Depends(...)` referencing a **closure** inside an app factory
gets silently dropped by FastAPI → param becomes a query param → 422s. Fix:
module-level dependency + `app.dependency_overrides` (see `app/main.py`).

## 6. Environment notes

- `backend/.venv` exists (has fastapi, pydantic, psutil, pytest, ruff).
- Background processes may be running from previous sessions:
  - docs server on port 8000 (old `/root/jarvis` copy) — repoint to repo or kill
  - backend `uvicorn` on port 8010 — may or may not still be alive
- `pip` installs need a venv (system Python is PEP-668 managed).
- No `gh` CLI; pushes have worked via the remote URL's credentials.

## 7. Rules to always follow

- Update this file after every significant change (this is the session handoff).
- Keep the portability matrix as the source of truth for OS support.
- Never commit secrets (`.gitignore` covers `.env`, keys).
- macOS is the dev platform per spec — but the container here is Linux; don't
  block on macOS-only testing (CI covers it).