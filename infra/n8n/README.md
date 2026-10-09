# n8n workflow definitions (matrix row C6 — Hybrid/Remote)

Importable n8n workflow templates. n8n is the workflow engine for Hybrid/Remote
deployments (deployment modes B/C, see `docs/architecture/01-overview.md` and
ADR-0004); the JARVIS backend triggers them through their **webhook path** using
`POST {n8n_base}/webhook/<path>`, and the agent only runs paths on the
`JARVIS_ALLOWLIST_WEBHOOKS` allowlist (default-deny, like every other target).

## Files

| File | Webhook path | What it does |
|---|---|---|
| `daily-report.json` | `daily-report` | Returns a JSON report keyed by today's date, echoing the payload the agent posted |
| `weekly-digest.json` | `weekly-digest` | Aggregates a week's events (`payload.events`) into a per-day count |

Both follow the same shape — **Webhook → Code → Respond to Webhook** — so the
backend always gets a JSON response (the `N8nWorkflowProvider` also tolerates
plain-text responses when a workflow has no respond node).

## Importing

In the n8n UI (http://127.0.0.1:5678 when running via `infra/docker-compose.yml`):

1. **Workflows → ⋯ → Import from File**, pick `daily-report.json`.
2. Activate the workflow (toggle) so the webhook is live.
3. Confirm the webhook path matches the file name (it is the `path` on the
   Webhook node; mine already match the allowlist).

> The exact node parameters shipped here target current n8n (Webhook v2, Code
> v2, Respond to Webhook v2). Node schemas drift across n8n releases — if an
> import complains about a node, recreate just that node from the canvas
> palette and re-save; the webhook path and post-structure are the contract the
> backend depends on, not the node internals.

## Wiring to JARVIS

```bash
docker compose -f infra/docker-compose.yml up -d
# in the n8n UI: Settings → API → create an API key, then:
export JARVIS_N8N_BASE_URL=http://127.0.0.1:5678
export JARVIS_N8N_API_KEY=<your-key>
export JARVIS_ALLOWLIST_WEBHOOKS='["daily-report","weekly-digest"]'
```

Now `GET /api/workflow/list` returns both workflows, and the agent can run them
with the `workflow.run` tool (webhook path = allowlisted name, payload passed
under `input`).

### Local mode equivalent

Local-only mode (no n8n, no Docker) uses the in-process scheduler instead —
the same `daily-report` webhook path is then a **workflow id** in a
`JARVIS_WORKFLOWS_DIR` definition (`backend/app/workflows/local.py`). Keep
workflow ids aligned with these webhook paths so Hybrid and Local stay
drop-in for the agent.