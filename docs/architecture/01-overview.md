# JARVIS — Architecture Overview

## 1. System context

JARVIS is an AI automation platform: a conversational agent that can operate a
user's computer, run workflows, and integrate with external tools — across macOS,
Windows, and Linux, accessed from a desktop client or a browser.

The core business logic must **not depend on macOS APIs**. Everything platform-
specific is behind the OS abstraction (see ADR-0003) and the client shell's
plugin boundary.

## 2. Layered architecture

Six independently maintainable layers. Strict dependency direction:
**Client → Core → Workflow → Tool → Execution → Provider**. A layer may only depend
on layers below it.

```
┌───────────────────────────────────────────────────────────────┐
│ 1. Client layer                                               │
│    desktop UI (Tauri) · voice · chat · web client             │
│    Shared React/TS frontend; platform shell (Tauri 2)         │
├───────────────────────────────────────────────────────────────┤
│ 2. Core backend                                              │
│    auth · agent orchestration · memory · task state ·         │
│    policies · audit logs                                      │
│    (FastAPI, platform-independent)                            │
├───────────────────────────────────────────────────────────────┤
│ 3. Workflow layer                                            │
│    n8n workflows · triggers · integrations · scheduling ·     │
│    retries                                                    │
├───────────────────────────────────────────────────────────────┤
│ 4. Tool layer                                                │
│    MCP servers · application APIs · approved tools            │
├───────────────────────────────────────────────────────────────┤
│ 5. Execution layer                                           │
│    local machine workers · containerized workers · optional   │
│    remote workers                                             │
├───────────────────────────────────────────────────────────────┤
│ 6. Provider layer                                            │
│    replaceable AI models · speech recognition · TTS ·         │
│    data providers                                             │
└───────────────────────────────────────────────────────────────┘
```

### 2.1 Client layer

- **Shared frontend** (`frontend/`): chat, voice interaction, settings, policy
  approval UI. One codebase used by the desktop app and the browser client.
- **Desktop shell** (`apps/desktop/`): Tauri 2 host. Owns the *client-side* OS
  concerns: microphone capture, wake word, notifications, tray, autostart,
  clipboard (explicitly permitted), global hotkeys.
- **Browser client** (`apps/web/`): same frontend served by the backend; used in
  Remote deployment. No local machine access by itself.

Client↔backend transport: HTTP + WebSocket (events/streaming) with JWT/OIDC auth.
Desktop additionally exposes native capabilities to the frontend via Tauri IPC,
routed through a thin capability layer (see ADR-0001).

### 2.2 Core backend

Platform-independent FastAPI service. Modules:

- **auth** — OIDC/OAuth2, device-flow pairing for desktop, API keys for workers/tools.
- **orchestration** — agent loop, tool routing, planning, session management.
- **memory** — scoped long-term memory (user, project, session) in Postgres (or
  SQLite in local-only mode).
- **task_state** — durable task/job state, retries, cancellation.
- **policies** — per-command and per-capability allow/deny policy engine, approval
  queue for risky actions.
- **audit** — append-only audit log of every computer operation.

Runnable standalone with `uv run fastapi dev` (no Docker required). See ADR-0004.

### 2.3 Workflow layer

n8n deployed as a portable service via Docker Compose for Hybrid/Remote modes.
Local-only mode uses a lightweight scheduler in the backend instead, keeping the
desktop client Docker-free. Triggers, integrations, retries, and scheduling are
n8n concepts; the backend bridges workflow runs to the tool layer via MCP.

### 2.4 Tool layer

MCP servers exposing approved tools (filesystem, calendar, browser automation,
apps). Each tool is an independent process. Tools register with the backend;
availability is advertised at runtime.

### 2.5 Execution layer

Where computer operations actually happen:

- **Local machine worker** — runs on the user's machine. Owns the *backend-side*
  OS abstraction: application launching, file/dir operations, approved shell
  commands, process management, system info, notifications.
- **Containerized worker** — for sandboxed/side-effect-free operations.
- **Remote worker** — optional; only ever via explicit pairing (see ADR-0005).

### 2.6 Provider layer

Registry of replaceable providers behind interfaces:

- **LLM provider** — OpenAI-compatible interface; default model selection at
  implementation time.
- **STT / TTS providers** — speech recognition and text-to-speech.
- **Data providers** — contacts, calendar, etc.

## 3. OS abstraction (both sides of the wire)

Two separate platform boundaries, by design:

| Boundary | Owner | Implementations | Concern |
|---|---|---|---|
| Client shell plugins | Tauri shell (Rust/plugins) | macOS / Windows / Linux | mic, wake word, notifications, tray, autostart, clipboard, hotkeys |
| Backend local worker | Python adapters | `macos.py` / `windows.py` / `linux.py` | app launch, files, shell, processes, system info, notifications |

Both follow the same rules (ADR-0003):

1. **Common interface** — one API, per-platform implementation.
2. **Runtime capability detection** — query what is actually available on the
   running OS/desktop session; never assume.
3. **Graceful degradation** — an unsupported operation returns a typed
   `UnsupportedCapability` result, never a crash or a silent no-op.
4. **No dangerous substitution** — if the native feature is missing, the worker
   must *not* fall back to a shell equivalent that changes semantics (e.g. never
   emulate "move window" via a kill/relaunch, never emulate Wake Word via a
   polling loop that burns CPU indefinitely). The request surfaces as unsupported
   and the user is told why.

## 4. Deployment modes

One codebase, three deployment modes — no rewrite. Selected by configuration
(`JARVIS_DEPLOYMENT_MODE=local|hybrid|remote`).

```
                    ┌────────────┐
  A. Local-only     │ Desktop    │──local IPC──▶ local backend ──▶ workers/tools on
                    └────────────┘               │                this machine
                                                 └──▶ (workflow: in-backend scheduler)

                    ┌────────────┐
  B. Hybrid         │ Desktop    │──▶ local backend ──▶ private server
                    └────────────┘      │              n8n + orchestration services
                                        └──▶ local worker (paired, authorized)

                    ┌───────────────────────────────┐
  C. Remote         │ Server: backend + n8n + tools │
                    └───────────────────────────────┘
                        ▲ HTTP/WS, authenticated (browser or desktop client)
                        │
              local machine control requires a separately
              paired + authorized local worker (see §5)
```

### Backend runtime resolver

The backend can run three ways; resolved at startup in order:

1. **Bundled/embedded** — a pre-built backend process shipped with (or launched
   by) the desktop app. Default for Local/Hybrid; **no Docker required for the
   client**.
2. **Docker Compose** — for Hybrid/Remote, where n8n and server-side services run
   as portable containers (`infra/docker-compose.yml`).
3. **System service** — on a server, via the same Compose config or a systemd unit.

Local-only mode substitutes SQLite for Postgres and an in-process scheduler for
n8n, so the whole platform runs on a laptop with zero container dependency.

## 5. Security posture

- **Local worker pairing** — a remote server never gains unrestricted access to a
  user's machine. The local worker is explicitly paired (device-code flow), holds
  per-capability allowlists, and logs every operation to the audit log. See
  ADR-0005.
- **Policy engine** — every computer operation passes through policies before
  execution; high-risk operations require interactive approval from the client.
- **Secrets** — never in source code. OS keychain on macOS/Windows, Secret Service
  on Linux, env/secret refs in Compose.
- **No hardcoded paths** — home directories, usernames, and executable paths come
  from config + platform path abstraction (`platformdirs`-style), never literals.

## 6. Feature parity & known limitations

- The portability matrix (doc 02) is the single source of truth for what each
  platform supports.
- A capability is *advertised* only when implemented **and** tested on that OS.
  Nothing is "supported" by assumption.
- Known limitations are documented in the matrix and surfaced in the client UI
  (e.g. "Wake word unavailable on this system — manual trigger only").