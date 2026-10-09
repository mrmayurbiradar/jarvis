# Daily-work agent: the "Hello Jarvis" morning routine

> Your plan: open the Mac, say **"Hello Jarvis"**, and an agent + a set of
> workflows (n8n / MCP / local scheduler) start your day — emails, Jira,
> dev loop, meetings, learning, gold rate, news. This doc maps that plan to
> what's built, what's live right now, and what each remaining integration
> needs from you (credentials).

## The activation flow (target)

```
Mac opens → desktop app wakes (always-on, wakes with the machine)
         → "Hello Jarvis" (voice)
         → agent greets → "start my day" → Morning routine
         → briefing.now  : gold, weather, tasks, notes, approvals, news
         → mcp.jira.*    : your open tickets        (needs Jira creds)
         → mcp.email.*   : your unread email        (needs email creds)
         → dev-loop      : checkout/build/test      (needs allowlist + approval)
         → meetings      : Teams/schedule digest    (needs calendar bridge)
```

## What is LIVE right now (no credentials, verified end to end)

On the running backend (`:8010`) the agent already does, by voice or chat:

| You say | It does |
|---|---|
| `start my day` / `good morning` | **morning briefing** — real gold rate in INR (`₹13,068/g`), weather (your city via `JARVIS_BRIEFING_CITY`), open tasks, today's notes, pending approvals, and headlines from technology / business & markets / politics / India business & tax RSS feeds |
| `hello jarvis` | spoken greeting + what it can do |
| `add a task: …` / `what's my todo?` / `mark … done` | durable to-do list |
| `take a note: …` / `what did I note today?` | dated journal in the workspace (`~/Jarvis/notes/YYYY-MM-DD.md`) |
| `how's the weather?` / `what time is it?` | weather + time |
| `remember that …` / `what do you remember about …` | long-term memory |
| `list my files` / `read README.md` | workspace-scoped file access (traversal-blocked) |

Every call flows through the ADR-0005 gates (pairing token → default-deny
allowlist → human approval for risky tools) and lands in the append-only audit
log. The morning routine also runs on schedule: `morning-briefing.json`
(weekdays 08:55) and `POST /api/workflow/morning-briefing/run` on demand.

## Where each part of YOUR list maps

| Your daily item | Mechanism (now / next) | What it needs from you |
|---|---|---|
| Check emails | `mcp.email.unread` MCP server (built, tested) | Gmail app password (or work IMAP creds) → env `EMAIL_IMAP_*`, add server to `JARVIS_MCP_SERVERS`, enable `email-digest.json` |
| Check new Jira tickets | `mcp.jira.unresolved` MCP server (built, tested) | Atlassian API token → env `JIRA_*`, add server to `JARVIS_MCP_SERVERS`, enable `jira-triage.json` |
| Checkout / build / run / debug / fix | `dev-loop.json` workflow (built, disabled) | add your repo commands to `JARVIS_ALLOWLIST_COMMANDS`; each shell step still waits for **your** approval in the UI (gate 3) — the agent proposes, you authorize |
| Commit / raise PR / merge PR / resolve Jira | next slice — git/gh/`jira` MCP tools behind approvals; the audit log already records every step | approve the actions in the Approvals panel; optionally wire `gh` for PRs |
| Meetings on Teams | next slice — calendar/meeting bridge (Teams has no free public API; options: calendar digest via email, or n8n's Microsoft 365 nodes in Hybrid mode) | n8n server (or a calendar email digest) |
| Learning / interview prep | next slice — a `learning-digest` workflow curating trending topics (HN/Dev.to RSS already feed the briefing) + spaced-recall notes from `notes`/`memory` | nothing — can ship standalone |
| Gold rate | **live now** (`gold-api.com` + FX, keyless) | — |
| Politics / tax / corporate law / IT market news | **live now** (BBC politics+business, Economic Times, HN RSS) | tune the feeds in `app/tools/briefing.py::NEWS_FEEDS` |
| "Activates when I open my Mac" | **today:** open `:1420` in the browser, say "Hello Jarvis" (Chromium voice). **Native:** the Tauri desktop shell needs a wake-word layer — WKWebView doesn't expose Web Speech recognition, so add a macOS-native listener (SFSpeechRecognizer in a Tauri Rust command) that triggers the same briefing on wake | a dev machine with the Rust toolchain to run `apps/desktop` |

## Credentials you need to gather (nothing is committed, all env-only)

```
# backend/.env  (gitignored)
JARVIS_BRIEFING_CITY=Bengaluru
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=<atlassian api token>
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_USER=you@gmail.com
EMAIL_IMAP_PASSWORD=<gmail app password>
JARVIS_MCP_SERVERS='[{"name":"hello"},{"name":"jira"},{"name":"email"}]'
JARVIS_WORKFLOWS_DIR=/path/to/infra/workflows-local
JARVIS_ALLOWLIST_COMMANDS='["echo","git","npm","gh"]'
JARVIS_ALLOWLIST_WEBHOOKS='["morning-briefing","jira-triage","email-digest","dev-loop"]'
```

Then flip `"enabled": true` on the workflow JSONs you want. No restart needed
for workflow defs (the scheduler reloads on each tick); env changes need a
backend restart (`kill <uvicorn-pid> && bash restart_backend.sh`).

## Optional: full conversational intelligence

The default `local` provider handles the fixed daily-work intents. For
open-ended reasoning ("summarize this Jira and draft the PR description"),
set:

```
JARVIS_LLM_PROVIDER=openai
JARVIS_OPENAI_API_KEY=<key>
JARVIS_OPENAI_MODEL=gpt-4o-mini
```

The same tools are then driven by the model instead of the intent router — no
other code changes.

## Why the security gates stay on

Your dev-loop, Jira and email actions touch real systems. The gates exist so
that even with full credentials, the agent **proposes** and you **approve**
(one click in the Approvals panel, or voice) before anything executes — and
every action is audited so you always know what ran. That's what makes an
always-on "Hello Jarvis" agent safe to leave running.