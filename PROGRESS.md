# JARVIS — Progress & Handoff

> Read this first in a fresh session. It summarizes what exists, what's next,
> and how to run/test everything.

**Last updated:** 2026-10-09 (session: clients started — shared frontend + web client verified, Tauri desktop shell scaffolded)

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
| `frontend/` | **Shared UI** (React 18 + TS + Vite, port 1420): pairing gate, Chat/Capabilities/Audit/Native tabs, `JarvisApi` client, token store, native-capability probing |
| `apps/web/` | Browser client (deployment mode C): builds the shared frontend as a static site; no local-access capabilities |
| `apps/desktop/` | **Tauri 2 desktop shell** (Layer 1, macOS/Windows/Linux): `src-tauri/` Rust with per-OS `platform/` modules mirroring ADR-0003; loads `frontend/dist` |

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
- **Shared frontend (done, verified here)**: React 18 + TS + Vite. Pairing
  flow (request/confirm), Chat (durable session_id), Capabilities, Audit,
  Native tabs. `JarvisApi` client + token store (localStorage), dark theme.
  tsc clean, 4 vitest tests pass, `vite build` → 151 kB JS (48.5 kB gzip).
- **Web client (done, verified here)**: `apps/web` builds the same frontend as
  a static site (mode C — browser has no local-computer access by design);
  `VITE_JARVIS_API` overrides the backend URL.
- **Tauri desktop shell (scaffolded, NOT yet `cargo check`ed)**: `apps/desktop`
  wraps the shared frontend. Rust `platform/` modules mirror ADR-0003
  (`CommandResult` = `ok|unsupported|failed`, per-OS `launch`, plugins for
  notification/clipboard/autostart). Needs the Rust toolchain on a dev machine.

### NOT done (designed only)
Workflows (n8n) · MCP tool servers · Postgres backing store · interactive
approval UI (gate 3 wired via `JARVIS_REQUIRE_APPROVAL`, UI pending) ·
`cargo check` of the Tauri shell on macOS/Windows/Linux · move token from
localStorage to the OS keychain.

## 4. Next steps (recommended order)

1. ~~Tauri desktop shell~~ — **scaffolded** (see §3). Next on this slice:
   `cargo check` on a machine with Rust (macOS: `xcode-select --install` first),
   then wire the gate-3 interactive approval prompt to the client.
2. **Workflow layer (n8n)** — Docker Compose service + bridge to the tool layer.
3. **MCP tool servers** — filesystem/calendar/etc. as independent processes.
4. **Postgres backing store** for Hybrid/Remote (swap store behind an interface).
5. **Polish clients**: OS keychain for the token, tray icon + autostart toggle
   UI, voice (mic) → wake-word (P2), global hotkey (P2).

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

### Clients

```bash
# Shared frontend dev server (hot reload, port 1420)
cd /root/jarvis-repo/frontend && npm run dev

# Browser client (mode C — static build of the shared frontend)
cd /root/jarvis-repo/apps/web && npm run build && npx vite preview   # or any static host

# Desktop shell (needs Rust toolchain — run on a dev machine, not this container)
cd /root/jarvis-repo/apps/desktop && npm install && npm run dev
```

Frontend checks: `cd frontend && npx tsc -b && npx vitest run && npm run build`.
The web client is verified here; the desktop shell needs `cargo check` on macOS.

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
- Frontend dev server runs on port **1420** (Vite convention); backend default
  `http://127.0.0.1:8000`, override via `VITE_JARVIS_API` when running on
  another port.
- The container here has **no Rust/webkit toolchain** — the Tauri shell
  (`apps/desktop`) is unverified until `cargo check` runs on a dev machine.
  `@tauri-apps/cli` and `src-tauri/target/` are gitignored, so the scaffold
  still checks in clean.

## 7. Rules to always follow

- Update this file after every significant change (this is the session handoff).
- Keep the portability matrix as the source of truth for OS support.
- Never commit secrets (`.gitignore` covers `.env`, keys).
- macOS is the dev platform per spec — but the container here is Linux; don't
  block on macOS-only testing (CI covers it).
- Keep `frontend/` as the single source of truth for the UI; `apps/web` and
  `apps/desktop` both consume it (no UI forks).