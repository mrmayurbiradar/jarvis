# JARVIS — Repository Layout

Proposed monorepo structure. `backend/` is independently runnable and testable
(no Docker required). `apps/` and `frontend/` are the client layer. Everything
platform-specific is isolated behind the OS abstraction (ADR-0003).

```
jarvis/
├── README.md
├── docs/
│   ├── architecture/
│   │   ├── 01-overview.md
│   │   ├── 02-portability-matrix.md
│   │   └── adr/
│   │       ├── 0001-tauri-vs-electron.md
│   │       ├── 0002-python-fastapi-backend.md
│   │       ├── 0003-os-abstraction-interface.md
│   │       ├── 0004-backend-runtime-and-deployment-modes.md
│   │       └── 0005-local-worker-pairing-and-authorization.md
│   └── (user guides, operator guides — later)
│
├── backend/                       # CORE + WORKER + PROVIDER layers (Python)
│   ├── pyproject.toml             # uv-managed; `uv run fastapi dev` works standalone
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                # FastAPI app factory (deployment-mode aware)
│   │   ├── api/                   # HTTP + WS routes (v1)
│   │   ├── core/                  # auth, orchestration, memory, task_state,
│   │   │                          #   policies, audit — platform-independent
│   │   ├── workflows/             # local scheduler; n8n bridge (Hybrid/Remote)
│   │   ├── tools/                 # MCP client/server registration, approved tools
│   │   ├── execution/
│   │   │   ├── workers/           # local worker, containerized worker, remote client
│   │   │   └── platform/          # ★ OS abstraction (ADR-0003)
│   │   │       ├── base.py        #   PlatformAdapter ABC + UnsupportedCapability
│   │   │       ├── registry.py    #   runtime capability detection
│   │   │       ├── macos.py
│   │   │       ├── windows.py
│   │   │       └── linux.py
│   │   ├── providers/             # LLM, STT, TTS, data — replaceable
│   │   └── config.py              # pydantic-settings; env-specific config
│   └── tests/                     # pytest; platform-agnostic + per-OS marks
│       ├── unit/
│       ├── integration/
│       └── platform/              # macOS/Windows/Linux-specific tests
│
├── frontend/                      # shared React/TS UI (desktop + web)
│   └── src/                       # chat, voice, settings, policy approvals
│
├── apps/
│   ├── desktop/                   # Tauri 2 host (macOS first)
│   │   ├── package.json           # wraps shared frontend
│   │   ├── src-tauri/
│   │   │   ├── src/               # Rust: capability layer (A1–A11), IPC
│   │   │   ├── capabilities/      # Tauri capability/permission files
│   │   │   └── tauri.conf.json
│   │   └── installers/            # per-OS packaging (dmg/nsis/appimage)
│   └── web/                       # browser client (deployment mode C)
│
├── infra/
│   ├── docker-compose.yml         # portable services: backend, n8n, postgres
│   ├── docker-compose.local.yml   # local-only: backend + sqlite (no n8n)
│   └── n8n/                       # workflow definitions, trigger configs
│
├── tools/                         # MCP servers (each an independent process)
│   ├── filesystem/
│   ├── calendar/
│   └── ...
│
└── scripts/                       # CI, installers (platform-specific, opt-in)
```

## Key structural rules

1. **`backend/` has zero dependency on `frontend/`/`apps/`.** It can be run,
   tested, and containerized on its own.
2. **`backend/app/execution/platform/` is the only place with OS-specific code.**
   Everything else imports the ABC (`base.py`) and is tested platform-agnostically.
3. **Shared frontend** is imported by both the Tauri app and the web client — one
   UI codebase, per the spec's "shared frontend wherever practical".
4. **No secrets** in any file in this tree; only `.env.example` templates.
5. **No Docker required for the desktop client.** Desktop launches the backend as
   a bundled/embedded process in Local/Hybrid mode (ADR-0004).
6. Platform-specific *installation scripts* live under `scripts/` and are written
   only where necessary (per spec), never required for development.