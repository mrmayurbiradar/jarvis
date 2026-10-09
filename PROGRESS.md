# JARVIS — Progress & Handoff

> Read this first in a fresh session. It summarizes what exists, what's next,
> and how to run/test everything.

**Last updated:** 2026-10-09 (session: backend core complete — auth, agent, stores)

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

**Design: DONE.** **Backend core: DONE** (auth, agent, stores, policies, API).
Remaining: workflows (n8n), MCP tools, desktop/web clients, Docker live-test.

### Done (verified)
- Design docs + 5 ADRs + portability matrix (all committed).
- FastAPI app: `GET /healthz`, `GET /api/capabilities`, `POST /api/worker/shell`,
  `POST /api/chat`, `GET /api/audit`, `POST /api/pair/request|confirm`.
- `PlatformAdapter` ABC + macOS/Windows/Linux adapters; runtime detection;
  graceful `UnsupportedCapability`; no-dangerous-substitution rule.
- **Auth + pairing (ADR-0005)**: device-code pairing → bearer token; tokens
  stored hashed, constant-time verify, one-sided revocation.
- **Agent orchestration (matrix C2)**: LLM loop + tool routing. Tools:
  `shell.run`, `app.launch`, `system.info`, `memory.store`, `memory.recall`.
  Gates in order: pairing → policy → (opt-in) approval. Every op audited.
- **Provider layer (C7)**: `LlmProvider` interface; `mock` (keyless) + 
  `openai_compat` (stdlib-only urllib, works with any /v1/chat/completions).
- **Stores**: SQLite (`app/core/store.py`) — pairings, sessions, memory, audit
  (append-only), tasks. Local mode needs no containers (ADR-0004).
- **Docker Compose + Dockerfile** (`infra/`, `backend/Dockerfile`) for
  Hybrid/Remote — the desktop client never needs Docker.
- Tests: **39 passed, 8 skipped on Linux**; lint clean. CI matrix (3 OSes).
- End-to-end smoke verified on live server: pairing → chat → shell → audit.
- Pushed to GitHub (`9c5d5d6` → latest). CI configured for 3 OSes.

### NOT done (designed only)
Workflows (n8n) · MCP tool servers · Tauri desktop client · web client ·
Postgres backing store · interactive approval UI (gate 3 wired via
`JARVIS_REQUIRE_APPROVAL`, UI pending).

## 4. Next steps (recommended order)

1. **Tauri desktop shell** — wraps a shared frontend, owns mic/wake-word/
   clipboard (matrix A1–A11); wires the gate-3 approval prompt to the client.
2. **Workflow layer (n8n)** — Docker Compose service + bridge to the tool layer.
3. **MCP tool servers** — filesystem/calendar/etc. as independent processes.
4. **Postgres backing store** for Hybrid/Remote (swap store behind an interface).

Each slice should: implement → unit test (platform-agnostic) → update this file.

## 5. How to run / test

```bash
cd /root/jarvis-repo/backend
.venv/bin/python -m pytest              # 39 pass on Linux (venv already built)
# or via uv:  uv sync --extra dev && uv run pytest

# Run the server (allowlist needed for shell to return 200):
JARVIS_ALLOWLIST_COMMANDS='["echo"]' .venv/bin/uvicorn app.main:app --port 8010
# Interactive API docs: http://127.0.0.1:8010/docs

# Try the full flow:
#   1. POST /api/pair/request  {"display_name":"demo"}  -> 6-digit code
#   2. POST /api/pair/confirm  {"code":"..."}           -> bearer token
#   3. POST /api/chat  {"message":"hello"}  (Bearer token)  -> "(mock) hello"
#   4. GET  /api/audit (Bearer token) -> every operation logged
# Default LLM is "mock" (no key). Set JARVIS_LLM_PROVIDER=openai + key to go real.
```

Known gotcha (documented for posterity): with `from __future__ import
annotations`, a `Depends(...)` referencing a **closure** inside an app factory
gets silently dropped by FastAPI → param becomes a query param → 422s. Fix:
module-level dependency + `app.dependency_overrides` (see `app/main.py`).

## 6. Environment notes

- `backend/.venv` exists (has fastapi, pydantic, psutil, pytest, ruff).
- No background servers left running (uvicorn on 8010/8011 were stopped after
  smoke tests). Restart with the command above when needed.
- `pip` installs need a venv (system Python is PEP-668 managed).
- No `gh` CLI; pushes have worked via the remote URL's credentials.
- Test gotcha: agent tool outcomes are fed back to the LLM, so policy-deny /
  unsupported / blocked assertions must check the tool message content
  (`result.messages`), not the final `result.text` (see `tests/unit/test_agent.py`).

## 7. Rules to always follow

- Update this file after every significant change (this is the session handoff).
- Keep the portability matrix as the source of truth for OS support.
- Never commit secrets (`.gitignore` covers `.env`, keys).
- macOS is the dev platform per spec — but the container here is Linux; don't
  block on macOS-only testing (CI covers it).