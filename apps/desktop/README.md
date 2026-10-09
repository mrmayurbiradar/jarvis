# JARVIS Desktop (Tauri 2)

The native desktop shell for JARVIS. It loads the **shared frontend**
(`frontend/`) inside a lightweight OS webview via Tauri 2, and exposes
platform capabilities (notifications, clipboard, autostart, launch-application)
to the UI over Tauri commands.

This is the Layer 1 "Client" implementation for macOS / Windows / Linux.
Browser access is the separate `apps/web` client (deployment mode C).

## Layout

```
apps/desktop/
  package.json              # tauri CLI scripts (dev / build)
  src-tauri/
    Cargo.toml              # tauri 2 + plugins (notification, clipboard, autostart)
    tauri.conf.json         # window, dev URL, frontendDist, bundle
    capabilities/default.json   # permissions for the main window
    icons/icon.png          # placeholder app icon (regenerate for release)
    src/
      main.rs               # thin entry point
      lib.rs                # Builder + plugins + command handler
      platform/
        mod.rs              # CommandResult (Ok|Unsupported|Failed) + cross-platform commands
        macos.rs            # launch via `open`
        windows.rs          # launch via `cmd /c start`
        linux.rs            # launch via `xdg-open` / `gio open`
```

## Portability contract

Every command returns a `CommandResult` with a `status` tag matching the
frontend type in `frontend/src/native.ts`:

- `ok` — capability worked, `value` holds the result
- `unsupported` — capability genuinely absent on this OS, with a `reason`
  (UI degrades gracefully, never crashes)
- `failed` — capability present but errored, with `code` + `message`

Per the architecture spec (ADR-0002), an unavailable capability is **never**
silently substituted with a different, potentially dangerous command.

## Run

Requires the Rust toolchain (`rustup`) plus OS webview deps:

- macOS: Xcode command-line tools
- Windows: WebView2 (preinstalled on Win 10/11)
- Linux: `webkit2gtk-4.1`, `libappindicator`, `librsvg` (see your distro's
  Tauri prerequisites)

```bash
# from repo root
cd apps/desktop
npm install                 # installs @tauri-apps/cli
npm run dev                 # starts the frontend dev server + opens the window
```

For a release bundle (`.app` / `.msi` / `.deb`):

```bash
npm run build
```

The app talks to the backend at `http://127.0.0.1:8000` by default (start it
with `uv run uvicorn backend.app.main:app`). In the browser/web client this is
overridable with `VITE_JARVIS_API`.

> **Status:** the Rust shell in this directory is scaffolding written against
> the Tauri 2 API. It has NOT been `cargo check`ed in CI yet — run
> `cargo check` here before relying on it (first Tauri build also downloads
> several hundred crates, so expect it to be slow).