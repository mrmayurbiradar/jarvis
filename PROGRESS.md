# JARVIS — Progress & Handoff

> Read this first in a fresh session. It summarizes what exists, what's next,
> and how to run/test everything.

**Last updated:** 2026-10-09 (session: **daily-work agent brain** — the app now
actually *does* your daily work when you talk to it, no API key needed.
Default LLM is now `local`: a keyless intent-routing provider
(`app/providers/local.py`) that turns plain English ("add a task: buy
groceries", "what's my todo?", "how's the weather?") into real tool calls and
speakable replies. New daily-work tools (`app/tools/daily.py`): tasks
add/list/done (SQLite `tasks` table), notes append/today (dated journal in the
workspace), weather (wttr.in, no key), workspace-scoped files list/read. 120
backend + 15 frontend tests passing; live app on :8010/:1420 with workspace at
/root/Jarvis)

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
**Gate-3 approval loop: DONE** (backend queue + respond AND the client UI —
poll, badge, approve/deny buttons). **CORS: DONE** (browser/desktop clients
reach the API cross-origin). Remaining: Postgres backing store, `cargo check`
of the Tauri shell, live `docker compose up` smoke test (n8n + Postgres).

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
- **Gate-3 approval UI (shared frontend, done + verified)**: new **Approvals**
  tab (`ApprovalsView.tsx`) polls `GET /api/approvals/pending` every 5s and
  renders a card per pending action (capability chip + args), with Approve /
  Deny buttons that POST `/api/approvals/{id}/respond` and show the tool
  result. The tab in `App.tsx` shows a **live red badge** with the pending
  count (polled even when the tab is closed — a scheduled job or chat request
  lights it up). API client methods + 2 new vitest tests. The full
  ADR-0005 gate-3 loop now works end to end in the browser.
- **CORS middleware** (`app/main.py`): the browser (Vite :1420) and Tauri
  webview call the API cross-origin with a bearer token (never cookies), so
  wildcard CORS is safe and required for the web/desktop clients. Preflight
  test added.
- **Voice layer (client-side STT/TTS, zero deps)** — `frontend/src/voice.ts`:
  browser Web Speech API. Push-to-talk 🎤 (click, speak, reply spoken aloud
  at a lower "JARVIS" pitch), a **"Hey Jarvis" wake word** toggle
  (experimental, continuous listening; matches the phrase, says "Yes, sir?",
  takes the next utterance as the command), and a "Speaks" toggle to silence
  replies. Feature-detected with a graceful note (mic needs a secure context:
  `http://localhost` or https; Chromium browsers). Pure helpers
  (`stripMockPrefix`, `wakeMatch`, `pickEnglishVoice`) unit-tested. Backend
  provider-level STT/TTS (C7, e.g. Whisper + Porcupine) remains the P2 route.
- Tests: **105 passed, 8 skipped on Linux**; lint clean (ruff). CI matrix (3 OSes).
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
Postgres backing store · `cargo check` of the Tauri shell on
macOS/Windows/Linux · move token from localStorage to the OS keychain ·
live `docker compose up` smoke test (n8n + Postgres) · calendar/email MCP
servers (filesystem + hello exist as reference implementations).

## 4. Next steps (recommended order)

1. ~~Approval UI~~ — **done** (Approvals tab + live badge + approve/deny;
   verified end to end in the live app). 
2. **Live `docker compose up` smoke test** (n8n + Postgres): import the
   templates in `infra/n8n/`, then `GET /api/workflow/health` through the
   backend in Hybrid mode.
3. **Postgres backing store** for Hybrid/Remote (swap store behind an interface).
4. ~~MCP tool servers~~ — **done** (protocol + hello/filesystem + bridge).
   Next: real servers (calendar, email) reusing `app/mcp/servers/filesystem.py`
   as the reference shape.
5. **Polish clients**: OS keychain for the token, tray icon + autostart toggle
   UI, global hotkey (P2). Voice (P2): wake word + continuous listening is
   working experimentally in-browser (Web Speech API); the full route is
   backend STT/TTS providers (C7 — Whisper, Porcupine/Picovoice) wired through
   `LlmProvider`-style abstraction.
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
JARVIS_ALLOWLIST_WEBHOOKS='["daily-report","system-health","demo-approval"]' \
JARVIS_REQUIRE_APPROVAL=true \
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010
# Interactive API docs: http://127.0.0.1:8010/docs

# Run the UI (shared frontend, points at the backend):
VITE_JARVIS_API=http://127.0.0.1:8010 npm run dev -- --host 0.0.0.0 --port 1420
# Open http://127.0.0.1:1420 — pair once (code on screen), then:
#   Approvals tab (red badge = actions waiting) → Approve/Deny → Audit log shows it.

# Full flow:
#   1. POST /api/pair/request {"display_name":"demo"} -> 6-digit code
#   2. POST /api/pair/confirm {"code":"..."}          -> bearer token
#   3. POST /api/chat {"message":"hello"} (Bearer)    -> "(mock) hello"
#   4. GET  /api/workflow/health|list (Bearer)        -> local scheduler status
#   5. GET  /api/approvals/pending (Bearer)           -> queued gate-3 actions
#   6. POST /api/approvals/{id}/respond {"decision":"approve"|"deny"}
#   7. GET  /api/audit (Bearer)                       -> every operation logged
# Default LLM is "mock" (no key). Set JARVIS_LLM_PROVIDER=openai + key to go real.
# The demo-approval workflow (60s interval) queues a shell approval every
# minute so the UI badge has something to show.

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

Backend checks: `cd backend && source .venv/bin/activate && python -m pytest tests/unit`.
The live backend is launched by `$CLAUDE_JOB_DIR/tmp/restart_backend.sh` — it
exports the env (incl. `JARVIS_WORKSPACE_DIR=/root/Jarvis`, NOT `JARVIS_WORKSPACE`
— pydantic-settings maps `JARVIS_<FIELD>` so the field `workspace_dir` needs the
`_DIR` suffix; a mistyped name is silently ignored due to `extra="ignore"`).
Uvicorn must be restarted by killing its PID first — a `pkill -f` in the same
bash line self-matches the invoking shell and kills the whole command.

## 6. Environment notes

- **Command Center art reference**: `https://jarvis.institute/page-art/jarvis-command-center-real.webp`
  (alt: "Jarvis AI Assistant Command Center with AI core, active agents, tasks,
  and quick commands" — i.e. one screen for task, tool activity, approvals,
  result). Palette extracted via Pillow (base #051221, accents #006080/#007090/
  #1080a0) and mapped to CSS vars in `frontend/src/styles.css` (--bg #040d1a,
  --cyan #38d6f5 family).
- `backend/.venv` exists (has fastapi, pydantic, psutil, pytest, ruff).
- **The live app is running right now** (as of this update): backend uvicorn
  on :8010 (all layers: local scheduler + MCP hello + gate-3 approvals) and
  the Vite dev server on :1420 serving the shared frontend. Restart with the
  commands in §5 if they stop.
- `frontend/node_modules` needs `npm install` after a fresh clone (gitignored).
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