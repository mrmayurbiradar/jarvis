# ADR-0004: Backend runtime & deployment modes

- **Status:** Accepted
- **Date:** 2026-10 (baseline decision)
- **Owner:** Core backend, Infrastructure

## Context

The spec requires three deployment modes supported without rewriting the
application — **Local-only (A)**, **Hybrid (B)**, **Remote (C)** — and states:
"Run portable backend services through Docker Compose where appropriate" and
"Do not require Docker for the desktop client itself."

## Decision

One backend codebase; deployment mode selected by configuration
(`JARVIS_DEPLOYMENT_MODE=local|hybrid|remote`) and by which *runtime* the backend
starts under. The backend exposes the same API in all modes; only the backing
stores and workflow engine differ.

### Runtime resolver (startup order)

1. **Bundled/embedded backend** — a self-contained backend process shipped with
   (or launched by) the desktop app. Default for Local and Hybrid. No Docker.
2. **Docker Compose** — `infra/docker-compose.yml` for Hybrid/Remote
   (backend + n8n + Postgres) and `docker-compose.local.yml` for Local
   (backend + SQLite, no n8n). Used when Docker is available and preferred.
3. **System service** — systemd unit / Windows service / launchd for a server
   install; same Compose config underneath.

### Per-mode configuration

| Concern | A. Local-only | B. Hybrid | C. Remote |
|---|---|---|---|
| Client | Desktop | Desktop | Browser or Desktop |
| Backend runtime | Bundled (default) or Compose-local | Bundled, connecting to private server services | Server service |
| Workflow engine | In-process scheduler (no n8n) | n8n on private server | n8n on server |
| Memory/task store | SQLite | Postgres (server) | Postgres (server) |
| Auth | Local (device pairing) | Local + server | Server (OIDC) |
| Local computer control | Local worker, always available | Local worker, paired + authorized | Requires separately paired + authorized local worker (ADR-0005); otherwise no local machine access |

### Desktop client has zero Docker dependency

- Local/Hybrid default path: the desktop app launches the bundled backend process
  directly (`backend/dist/` built by `uv build`/PyInstaller).
- Docker is offered as an *option* for users who prefer containers — never a
  requirement to run the client.

## Consequences / mitigations

- **SQLite vs Postgres** is an implementation detail of the store layer (matrix
  row C3); both back the same repository interfaces, so swapping mode is config,
  not code.
- **Workflow parity:** local mode's scheduler implements the same trigger/retry
  semantics as n8n for the subset that runs on a laptop; the n8n bridge is
  mocked in local-mode tests (matrix row C6).
- **CI:** the backend test suite runs in all three modes on macOS, Windows and
  Linux runners (matrix row D3).

## Links

- Portability matrix C1–C7 (core backend) and D3
- ADR-0002 (Python/FastAPI)
- ADR-0005 (local worker pairing & authorization)
- `infra/docker-compose*.yml` (repository layout)