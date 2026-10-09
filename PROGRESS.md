# JARVIS — Progress & Handoff

> Read this first in a fresh session. It summarizes what exists, what's next,
> and how to run/test everything.

**Last updated:** 2026-10-09 (session: workflows local scheduler + n8n defs +
MCP tool servers + gate-3 approval backend done; 104 tests passing; live E2E
verified on uvicorn)

## 1. What the project is

Cross-platform AI automation platform ("JARVIS"): an AI assistant that operates
the user's computer (launch apps, run approved shell commands, files, etc.)
across macOS / Windows / Linux, from a desktop (Tauri) or browser client.

- Repo: `https://github.com/mrmayurbiradar/jarvis` (remote `origin`, branch `main`)
- Local clone: `/root/jarvis` (this is the live repo — `git log` + origin match)

## 2. Where things live

| Path | What it is |
|---|---|
| `docs/architecture/01-overview.md` | 6-layer architecture, deployment modes, security posture |
| `docs/architecture/02-portability-matrix.md` | **The spec deliverable**: every capability × OS × deps × verification test |
| `docs/architecture/03-repository-layout.md` | Monorepo layout |
| `docs/architecture/adr/0001-0005` | Decisions: Tauri, FastAPI, OS abstraction, deployment, worker auth |
| `backend/` | FastAPI core backend — the only code so far |
| `backend/app/execution/platform/` | **OS abstraction** (ADR-0003): `base.py` + `macos/windows/linux.py` + `registry.py` |
| `backend/app/workflows/` | **Workflow layer** (matrix C6): `WorkflowProvider` ABC + `N8nWorkflowProvider` (stdlib urllib) + **`LocalSchedulerWorkflowProvider`** (in-process scheduler, Local mode) |
| `backend/app/workflows/schedule.py` | Schedule primitives: `IntervalSchedule` + `CronSchedule` (5-field, `*/n`, ranges, lists, `?`) |
| `backend/app/mcp/` | **MCP (Layer 4)**: stdio JSON-RPC 2.0 protocol (`protocol.py`), server base (`server.py`), servers `hello` + `filesystem` (default-deny path jail) |
| `backend/app/tools/mcp.py` | `McpClient` (spawns server subprocess) + `McpToolBridge` → agent tools named `mcp.<server>.<tool>` |
| `backend/app/api/approvals.py` | **Gate-3 approval surface**: `GET /api/approvals/pending` + `POST /api/approvals/{id}/respond` |
| `backend/app/api/workflow.py` | `/api/workflow/health|list` — 501 unconfigured, 502 engine down (graceful) |
| `backend/app/core/policies.py` | Default-deny shell allowlist (ADR-0005 gate 2) |
| `backend/app/core/store.py` | SQLite stores: pairings, sessions, memory, audit (append-only), tasks, **approvals** |
| `backend/app/config.py` | Env-driven settings; `workflows_dir`, `mcp_servers`, webhook allowlist |
| `infra/n8n/` | **n8n v1 workflow templates** (daily-report, weekly-digest) + import README (Hybrid/Remote) |
| `infra/workflows-local/` | **Local scheduler workflow defs** (daily-report, system-health) + format README |
| `backend/tests/` | `unit/` (platform-agnostic, fake adapter) + `platform/` (per-OS, CI runners) |
| `.github/workflows/backend.yml` | CI: runs backend tests on macOS/Windows/Linux |
| `frontend/` | **Shared UI** (React 18 + TS + Vite, port 1420): pairing, Chat/Capabilities/Audit/Native tabs, `JarvisApi` client, token store |
| `apps/web/` | Browser client (deployment mode C): builds the shared frontend as a static site |
| `apps/desktop/` | **Tauri 2 desktop shell** (Layer 1): `src-tauri/` Rust with per-OS `platform/` modules mirroring ADR-0003; loads `frontend/dist` |

## 3. Current state

**Design: DONE. Backend core: DONE** (auth, agent, stores, policies, API).
**Workflows: DONE** (local in-process scheduler + n8n defs + n8n bridge).
**MCP tool servers: DONE** (protocol + hello/filesystem servers + agent bridge).
**Gate-3 approval backend: DONE** (queue + respond, audited). Remaining:
client UI wiring for approvals, Postgres backing store, `cargo check` of the
Tauri shell, live `docker compose up` smoke test.

### Done (verified)
- Design docs + 5 ADRs + portability matrix (all committed).
- FastAPI app: `GET /healthz`, `GET /api/capabilities`, `POST /api/worker/shell`,
  `POST /api/chat`, `GET /api/audit`, `POST /api/pair/request|confirm`,
  `GET /api/approvals/pending`, `POST /api/approvals/{id}/respond`,
  `GET /api/workflow/health|list`.
- `PlatformAdapter` ABC + macOS/Windows/Linux adapters; runtime detection;
  graceful `UnsupportedCapability`; no-dangerous-substitution rule.
- **Auth + pairing (ADR-0005)**: device-code pairing → bearer token; tokens
  stored hashed, constant-time verify, one-sided revocation.
- **Agent orchestration (matrix C2)**: LLM loop + tool routing. Tools:
  `shell.run`, `app.launch`, `system.info`, `memory.store`, `memory.recall`,
  `workflow.list`, `workflow.run`, `mcp.<server>.<tool>` (when configured).
  Gates in order: pairing → policy → approval. Every op audited.
- **Provider layer (C7)**: `LlmProvider` interface; `mock` (keyless) +
  `openai_compat` (stdlib-only urllib, works with any /v1/chat/completions).
- **Stores**: SQLite (`app/core/store.py`) — pairings, sessions, memory, audit
  (append-only), tasks, approvals. Local mode needs no containers (ADR-0004).
- **Workflow layer (matrix C6)**:
  - *Local half*: `LocalSchedulerWorkflowProvider` — stdlib `threading` daemon
    that loads `*.json` workflow defs from `JARVIS_WORKFLOWS_DIR`, schedules
    via interval or 5-field cron, and runs each step **through the agent's
    policy → approval → audit path** (`agent.execute` as step runner). Manual
    `run_workflow` interpolates `{{input.<key>}}` payload templates.
  - *Hybrid/Remote half*: `N8nWorkflowProvider` (urllib: health/list/webhook
    run) + n8n v1 workflow templates under `infra/n8n/`.
  - Tools `workflow.list` (read-only) + `workflow.run` (default-deny webhook
    allowlist, requires approval like shell). n8n wins when both engines set.
- **MCP tool servers (Layer 4)**: stdio JSON-RPC 2.0 with Content-Length
  framing (`initialize`, `notifications/initialized`, `tools/list`,
  `tools/call`). `McpToolBridge` spawns each server as an independent process
  (`python -m app.mcp.servers.<name>`), bridges tools to the agent as
  `mcp.<server>.<tool>`, degrades to "unavailable" (never crashes) when a
  server is missing. Servers: `hello` (fixture), `filesystem` (default-deny
  root jail — path escape attempts rejected). Configure via
  `JARVIS_MCP_SERVERS='[{"name":"filesystem","root":"/path"}]'`.
- **Gate-3 approval backend (ADR-0005)**: a `requires_approval` tool with
  `JARVIS_REQUIRE_APPROVAL=1` no longer just blocks — it queues a **pending
  approval record** (capability + args) and reports the id. Client polls
  `GET /api/approvals/pending`; `POST /api/approvals/{id}/respond` with
  `approve` re-runs the action through gates 1-2 and audits `allow/ok`, with
  `deny` audits `deny/rejected`. Double-respond → 409, unknown → 404,
  bad decision → 422. UI wiring is the client's job (not yet done).
- **Docker Compose + Dockerfile** (`infra/`, `backend/Dockerfile`) for
  Hybrid/Remote — the desktop client never needs Docker.
- Tests: **104 passed, 8 skipped on Linux**; lint clean (ruff). CI matrix (3 OSes).
- **Live E2E verified on uvicorn :8010** (all layers at once):
  pairing → capabilities (MCP advertised) → chat (mock) → worker shell
  (allowlisted 200 / `rm -rf /` 403) → workflow health/list (local scheduler,
  3 workflows) → scheduler tick fired a demo workflow: `system.info` ✓,
  `mcp.hello.greet` ✓ (real MCP subprocess), `shell.run` → blocked (gate 3) →
  human approved (executed + audited `allow/ok`) and denied (audited
  `deny/rejected`). Audit log showed every op.
- **Shared frontend (done, verified here)**: React 18 + TS + Vite. Pairing
  flow, Chat (durable session_id), Capabilities, Audit, Native tabs. `JarvisApi`
  client + token store (localStorage), dark theme. tsc clean, 4 vitest tests
  pass, `vite build` → 151 kB JS (48.5 kB gzip).
- **Web client (done, verified here)**: `apps/web` builds the same frontend as
  a static site (mode C); `VITE_JARVIS_API` overrides the backend URL.
- **Tauri desktop shell (scaffolded, NOT yet `cargo check`ed)**: `apps/desktop`
  wraps the shared frontend. Rust `platform/` modules mirror ADR-0003. Needs
  the Rust toolchain on a dev machine.

### NOT done (designed only)
Interactive approval UI (gate-3 backend done; the client polling/prompt is
next) · Postgres backing store · `cargo check` of the Tauri shell on
macOS/Windows/Linux · move token from localStorage to the OS keychain ·
live `docker compose up` smoke test (n8n + Postgres) · calendar/email MCP
servers (filesystem + hello exist as reference implementations).

## 4. Next steps (recommended order)

1. **Approval UI in the shared frontend**: poll `GET /api/approvals/pending`,
   render a prompt with the capability + args, POST `approve|deny`. Wire to
   the Chat/Native tabs. Backend is done and tested — this is the last piece
   of the ADR-0005 gate-3 loop.
2. ~~Workflow layer~~ — **done** (local scheduler + n8n defs + n8n bridge).
   Remaining: live `docker compose up` smoke test (n8n import the templates in
   `infra/n8n/`, then `GET /api/workflow/health` through the backend).
3. **Postgres backing store** for Hybrid/Remote (swap store behind an interface).
4. ~~MCP tool servers~~ — **done** (protocol + hello/filesystem + bridge).
   Next: real servers (calendar, email) reusing `app/mcp/servers/filesystem.py`
   as the reference shape.
5. **Polish clients**: OS keychain for the token, tray icon + autostart toggle
   UI, voice (mic) → wake-word (P2), global hotkey (P2).
6. **Tauri shell**: `cargo check` on a machine with Rust (macOS:
   `xcode-select --install` first).

## 5. How to run / test

```bash
cd /root/jarvis/backend
uv run pytest              # 104 pass + 8 skipped on Linux
uv run ruff check app tests

# Run the server — Local mode with everything on:
JARVIS_WORKFLOWS_DIR=../infra/workflows-local \
JARVIS_MCP_SERVERS='[{"name":"hello"}]' \
JARVIS_ALLOWLIST_COMMANDS='["echo"]' \
JARVIS_ALLOWLIST_WEBHOOKS='["daily-report","system-health"]' \
JARVIS_REQUIRE_APPROVAL=true \
.venv/bin/uvicorn app.main:app --port 8010
# Interactive API docs: http://127.0.0.1:8010/docs

# Full flow:
#   1. POST /api/pair/request {"display_name":"demo"} -> 6-digit code
#   2. POST /api/pair/confirm {"code":"..."}          -> bearer token
#   3. POST /api/chat {"message":"hello"} (Bearer)    -> "(mock) hello"
#   4. GET  /api/workflow/health|list (Bearer)        -> local scheduler status
#   5. GET  /api/approvals/pending (Bearer)           -> queued gate-3 actions
#   6. POST /api/approvals/{id}/respond {"decision":"approve"|"deny"}
#   7. GET  /api/audit (Bearer)                       -> every operation logged
# Default LLM is "mock" (no key). Set JARVIS_LLM_PROVIDER=openai + key to go real.

# Workflow layer (n8n, matrix C6 — Hybrid/Remote):
#   docker compose -f infra/docker-compose.yml up -d   # starts backend + n8n
#   n8n UI: http://127.0.0.1:5678 (Settings → API → create key)
#   Import infra/n8n/*.json via Workflows → Import from File
#   export JARVIS_N8N_BASE_URL=http://127.0.0.1:5678 JARVIS_N8N_API_KEY=...
#   JARVIS_ALLOWLIST_WEBHOOKS='["daily-report"]'
```

### Clients

```bash
# Shared frontend dev server (hot reload, port 1420)
cd /root/jarvis/frontend && npm run dev

# Browser client (mode C — static build of the shared frontend)
cd /root/jarvis/apps/web && npm run build && npx vite preview

# Desktop shell (needs Rust toolchain — run on a dev machine, not this container)
cd /root/jarvis/apps/desktop && npm install && npm run dev
```

Frontend checks: `cd frontend && npx tsc -b && npx vitest run && npm run build`.

Known gotcha (documented for posterity): with `from __future__ import
annotations`, a `Depends(...)` referencing a **closure** inside an app factory
gets silently dropped by FastAPI → param becomes a query param → 422s. Fix:
module-level dependency + `app.dependency_overrides` (see `app/main.py`).

## 6. Environment notes

- `backend/.venv` exists (has fastapi, pydantic, psutil, pytest, ruff).
- No background servers left running (uvicorn was stopped after the live E2E).
  Restart with the command above when needed.
- `pip` installs need a venv (system Python is PEP-668 managed).
- No `gh` CLI; pushes have worked via the remote URL's credentials.
- Test gotcha: agent tool outcomes are fed back to the LLM, so policy-deny /
  unsupported / blocked assertions must check the tool message content
  (`result.messages`), not the final `result.text` (see `tests/unit/test_agent.py`).
- Frontend dev server runs on port **1420**; backend default
  `http://127.0.0.1:8000`, override via `VITE_JARVIS_API`.
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