# JARVIS Startup Guide

This guide runs JARVIS in Local mode: a FastAPI backend and the shared UI. Launch the UI in a browser or the Tauri desktop shell. The Tauri dev shell is verified on macOS; Windows/Linux desktop builds are not yet checked.

## Prerequisites

- macOS, Windows, or Linux
- Python 3.12 or newer
- Node.js 18 or newer with npm
- Internet access to install dependencies. OpenRouter, weather, and some briefing tools also need network access.

Commands below use macOS/Linux shell syntax. On Windows, create the virtual environment with `py -m venv .venv` and activate it with `.venv\\Scripts\\activate`.

## 1. Install backend dependencies

From the repository root:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The virtual environment is local to `backend/`; activate it again in any new terminal used to run the backend.

## 2. Configure the backend

Create the local environment file once:

```sh
cp .env.example .env
```

Edit `backend/.env`. The default provider is `local`: it needs no key and handles a limited set of daily-work intents. For basic use, the defaults are sufficient. The `.env` file is ignored by Git; do not commit API keys.

### Use OpenRouter

OpenRouter works through JARVIS's OpenAI-compatible chat-completions provider. Set these values in `backend/.env`:

```dotenv
JARVIS_LLM_PROVIDER=openai
JARVIS_OPENAI_BASE_URL=https://openrouter.ai/api/v1
JARVIS_OPENAI_MODEL=provider/model-id
JARVIS_OPENAI_API_KEY=your-openrouter-key
```

Replace `provider/model-id` with a model available to your OpenRouter account that supports tool/function calling. Keep the key private. The backend must be restarted after changing provider settings.

### Optional local workflows and MCP tools

To load the sample in-process workflows and the `hello` MCP server, add the following to `backend/.env`:

```dotenv
JARVIS_WORKFLOWS_DIR=../infra/workflows-local
JARVIS_MCP_SERVERS=[{"name":"hello"}]
JARVIS_ALLOWLIST_WEBHOOKS=["daily-report","system-health","morning-briefing"]
```

Only workflow IDs in `JARVIS_ALLOWLIST_WEBHOOKS` may be started through the agent. A workflow definition can also run on its configured schedule. Leave these settings unset if you do not want the local scheduler or MCP server.

Shell access is default-deny. If you explicitly need the example `echo` command, configure:

```dotenv
JARVIS_ALLOWLIST_COMMANDS=["echo"]
JARVIS_REQUIRE_APPROVAL=true
```

Only allow commands you have reviewed. With approvals enabled, gated actions wait for your decision in the app's **Approvals** view.

## 3. Start the backend

Run this from the `backend/` directory with its virtual environment active:

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Leave this terminal open. Verify the API in another terminal or browser:

```sh
curl http://127.0.0.1:8010/healthz
```

Expected response: `{"status":"ok","deployment_mode":"local"}`. Interactive API documentation is at [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs).

## 4. Start the browser UI

Open a second terminal from the repository root:

```sh
cd frontend
npm ci
VITE_JARVIS_API=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1 --port 1420
```

Open [http://127.0.0.1:1420](http://127.0.0.1:1420). Keep this terminal open too. Binding both services to `127.0.0.1` keeps them local to this computer.

### Run the Tauri desktop shell on macOS

Install Rust with `rustup` and Apple's Command Line Tools (`xcode-select --install`). Keep the backend running in its own terminal, then run from the repository root:

```sh
cd apps/desktop
PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH" npm install
PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH" \
VITE_JARVIS_API=http://127.0.0.1:8010 npm run dev
```

Tauri's dev hook starts the shared Vite frontend and opens the native window. On systems where Rust is already on `PATH`, the `PATH=...` prefix can be omitted. Stop the desktop app with **Ctrl+C** in its terminal.

## 5. Pair and try it

On the first visit:

1. Enter an optional display name and choose **Request pairing code**.
2. Enter the code shown on the page, then choose **Confirm pairing**.
3. Use the Command Center's quick prompts or open **Chat**.

With the default `local` provider, try requests such as `Add a task: buy groceries`, `What's my todo?`, `Take a note: call Sam at 4`, or `How's the weather in London?`. This provider uses intent matching rather than open-ended LLM reasoning. OpenRouter enables model-based responses, and the selected model must support tool calls for JARVIS actions.

The **Capabilities** view reports platform support, **Approvals** handles gated actions, and **Audit log** shows recorded operations. Chat voice controls depend on browser speech support.

## 6. Run checks

Backend tests, from `backend/` with the virtual environment active:

```sh
python -m pytest
```

Frontend tests and production build, from `frontend/`:

```sh
npm test
npm run build
```

## Stop and troubleshoot

- Stop each development server with **Ctrl+C** in its terminal.
- `401 Unauthorized`: pair the browser with the backend. If an old tab keeps failing, refresh it and pair again.
- OpenRouter errors: check that the key is valid, the account can access the selected model, and that model supports tool calling.
- Tauri microphone denied: quit and restart the desktop app after the plist change, then allow JARVIS under **System Settings → Privacy & Security → Microphone**. Browser runs need microphone permission for the site in browser settings.
- Port already in use: stop the process using `8010` or `1420`, or choose another port and update `VITE_JARVIS_API` to match the backend port.
- `uvicorn` or app imports not found: activate `backend/.venv` and run the command from `backend/`.

This guide covers Local mode. Hybrid/Remote deployments with Docker Compose and n8n are documented separately in `infra/` and the architecture docs. See `apps/desktop/README.md` for desktop-specific details.