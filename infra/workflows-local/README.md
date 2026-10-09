# Local scheduler workflow definitions (matrix row C6 — Local)

Sample JSON definitions for the **in-process scheduler** used by Local-only
deployment mode (ADR-0004: no n8n, no Docker on the desktop).

Each file is one workflow. Point the backend at this directory and the scheduler
loads them at runtime:

```bash
export JARVIS_WORKFLOWS_DIR=$PWD/infra/workflows-local
export JARVIS_ALLOWLIST_COMMANDS='["echo"]'   # shell.run steps are policy-gated
# webhook allowlist gates the workflow.run agent tool — use workflow ids:
export JARVIS_ALLOWLIST_WEBHOOKS='["daily-report","system-health","morning-briefing"]'
```

## The morning routine

Say **"start my day"** (or **"good morning"**) to the agent and it runs the
`briefing.now` tool: gold rate in INR, weather (JARVIS_BRIEFING_CITY), your
open tasks, today's notes, pending approvals, and headlines from technology /
business & markets / politics / India business & tax feeds — all keyless.

`morning-briefing.json` schedules the same digest on weekdays at 08:55, and
`POST /api/workflow/morning-briefing/run` fires it on demand.

### Planned workflows (disabled until you add credentials)

| Workflow | What it does | Needs |
|---|---|---|
| `jira-triage.json` | list your open Jira issues | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` + jira MCP server |
| `email-digest.json` | newest unread email subjects | `EMAIL_IMAP_HOST`, `EMAIL_IMAP_USER`, `EMAIL_IMAP_PASSWORD` + email MCP server |
| `dev-loop.json` | checkout → install → build → test | git/npm commands in `JARVIS_ALLOWLIST_COMMANDS`; each step still needs human approval (gate 3) |

Set the env, add the server to `JARVIS_MCP_SERVERS`, flip `"enabled": true`,
and they join the routine. See `docs/daily-work.md` for the full blueprint.

## Format

```json
{
  "id": "unique-id",              // == filename, and the id the agent uses to run it
  "name": "Human name",
  "description": "Optional",
  "enabled": true,
  "schedule": {                   // interval (seconds) or cron (UTC)
    "type": "cron",
    "expression": "0 9 * * *"    // or {"type": "interval", "seconds": 21600}
  },
  "steps": [
    {"tool": "shell.run",   "args": {"command": "echo hi"}},
    {"tool": "memory.store","args": {"fact": "remembered {{input.key}}"}}
  ]
}
```

- Steps invoke **agent tools** through the same policy → approval → audit path
  as a chat request (default-deny allowlists apply; nothing bypasses audit).
- String args can interpolate the run payload: `{{input.<key>}}`.
- Files that fail validation are skipped with a warning (`/api/workflow/health`
  reports `last_error`); the scheduler never crashes on a bad definition.

See `backend/app/workflows/local.py` and `backend/app/workflows/schedule.py`
for the exact contract, and the n8n templates in `../n8n/` for the Hybrid/Remote
equivalent of the same workflows.