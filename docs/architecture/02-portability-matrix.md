# JARVIS — OS Portability Matrix

**Status:** Baseline for the first release. Every capability below is the contract
that must be implemented and tested before it is advertised as supported on an OS.

Reading guide:

- **Owner** — which layer/component implements the capability.
  `CLIENT` = Tauri shell (Rust) + shared frontend. `WORKER` = backend local
  machine worker (Python adapters). `CORE` = platform-independent backend.
- **Impl** — the platform-specific implementation on each OS.
- **Deps** — third-party or OS dependencies; **not** the Python/Rust stdlib.
- **Test** — the verification test that must pass before the capability is
  advertised on that platform.
- Status legend: `P0` = must ship in first release · `P1` = next · `P2` = future.

Capability detection rules (from ADR-0003) apply to **all** rows:
at runtime, query the actual capability, and if missing return a typed
`UnsupportedCapability` — never crash, never silently substitute a dangerous
or semantically different command.

---

## A. Client shell — local machine capabilities (CLIENT)

| # | Capability | macOS | Windows 10/11 | Linux | Deps | Verification test |
|---|-----------|-------|---------------|-------|------|-------------------|
| A1 | **Application launching** (open app / URL / file with default handler) | `open -a <app>` / `open <url>` via `tauri-plugin-shell` with allowlist | `start`/`cmd /c start` or ShellExecute via `tauri-plugin-shell` allowlist | `xdg-open` via `tauri-plugin-shell` allowlist (respect `BROWSER`/`XDG_*`); fallback `gio open` | `tauri-plugin-shell` (Rust); allowlist config | Rust integration test: mock allowlist, launch each target type, assert process exists / default handler invoked; e2e on each OS |
| A2 | **File & directory operations** (pick, read, write, watch) | `tauri-plugin-fs` + `tauri-plugin-dialog` (native `NSOpenPanel`) | `tauri-plugin-fs` + `tauri-plugin-dialog` (Win32 file dialog) | `tauri-plugin-fs` + `tauri-plugin-dialog` (GTK file dialog; portal on Wayland) | `tauri-plugin-fs`, `tauri-plugin-dialog` | Rust test: temp dir create/read/write/delete, dialog mock; e2e opens picker on each OS |
| A3 | **Clipboard access (explicitly permitted)** | `tauri-plugin-clipboard-manager` (NSPasteboard) | `tauri-plugin-clipboard-manager` (Win32 clipboard) | `tauri-plugin-clipboard-manager` (wl-clipboard via portal / X11) | `tauri-plugin-clipboard-manager`; permission prompt + user setting | Rust test: write→read roundtrip text + image; permission-denied path returns `UnsupportedCapability` |
| A4 | **Notifications** (from client/worker) | `tauri-plugin-notification` (UNUserNotificationCenter) | `tauri-plugin-notification` (Windows toast) | `tauri-plugin-notification` (D-Bus `org.freedesktop.Notifications`); requires notification daemon | `tauri-plugin-notification` | Rust test: send notification, assert delivery callback; on headless CI assert graceful degradation |
| A5 | **Microphone access** | `MediaRecorder`/`getUserMedia` (WKWebView, TCC prompt) | `MediaRecorder`/`getUserMedia` (WebView2) | `MediaRecorder`/`getUserMedia` (WebKitGTK; PipeWire/ALSA backend) | WebView media permissions; OS permission prompt | e2e: record 1s audio, assert non-zero PCM; denied-permission path returns typed error |
| A6 | **Wake-word activation** | Picovoice Porcupine (native lib) via Rust, hotword while idle | same | same; requires working audio input (A5) | `porcupine` native lib, per-OS build | Rust test: feed prerecorded wake-word WAV → trigger; feed silence → no trigger; unsupported audio → degrade to manual trigger |
| A7 | **Startup integration (launch at login)** | `tauri-plugin-autostart` (SMAppService / LaunchAgent) | `tauri-plugin-autostart` (registry Run key) | `tauri-plugin-autostart` (XDG autostart `.desktop`) | `tauri-plugin-autostart` | Rust test: enable→assert OS-level registration→disable; verify per-OS location written |
| A8 | **Global hotkey** (optional trigger) | `tauri-plugin-global-shortcut` (Carbon/NS) | `tauri-plugin-global-shortcut` (RegisterHotKey) | `tauri-plugin-global-shortcut` (X11/Wayland; may need portal on Wayland) | `tauri-plugin-global-shortcut` | Rust test: register combo, simulate keypress, assert event; Wayland-unsupported → `UnsupportedCapability` |
| A9 | **Audio output (TTS/assistant voice)** | Web Audio / system audio output | same | same (PipeWire/PulseAudio) | WebView audio output; TTS provider | e2e: play generated TTS sample, assert output session active |
| A10 | **Window/tray lifecycle (background agent)** | `tauri-plugin-single-instance` + tray (menu bar) | `tauri-plugin-single-instance` + tray (taskbar) | `tauri-plugin-single-instance` + tray (status notifier / GTK) | `tauri-plugin-single-instance`, tray support | Rust test: second instance exits, focus first; tray menu renders + actions fire |
| A11 | **App updates** | `tauri-plugin-updater` (Sparkle-compatible) | `tauri-plugin-updater` (NSIS) | `tauri-plugin-updater` (AppImage/deb) | `tauri-plugin-updater`, signing certs | CI: staged update package installs over prior version on each OS |

## B. Backend local worker — computer operations (WORKER)

| # | Capability | macOS | Windows 10/11 | Linux | Deps | Verification test |
|---|-----------|-------|---------------|-------|------|-------------------|
| B1 | **Application launching** (by name/URL, via worker) | `subprocess` → `open`; app-bundle resolution via LaunchServices (`lsregister`) | `os.startfile` / `subprocess` → `explorer.exe`; App Paths registry lookup | `subprocess` → `xdg-open`; `$PATH`/`.desktop` resolution | `pyobjc` (optional), stdlib `subprocess` | `pytest` per-OS: launch app → assert PID alive; unknown app → typed error, no silent fallback |
| B2 | **File & directory operations** | stdlib `pathlib`/`shutil` | same | same | stdlib | `pytest`: temp-tree CRUD, symlink, permissions, long paths (>260 on Win via `\\?\`), cross-drive |
| B3 | **Approved shell commands** (allowlisted) | `subprocess` with allowlist; `zsh`/`bash` chosen from config, never hardcoded | `subprocess` with allowlist; `powershell.exe -NoProfile` / `cmd` per config | `subprocess` with allowlist; shell from config (`$SHELL`→safe default) | stdlib; allowlist policy in CORE | `pytest`: allowlisted command runs; non-allowlisted rejected before spawn; unsupported shell → error |
| B4 | **Process management** (list/inspect/terminate) | `psutil` (proc_pidinfo) | `psutil` (Toolhelp/`CreateToolhelp32Snapshot`) | `psutil` (`/proc`) | `psutil` | `pytest`: spawn child, list, signal, assert state transitions |
| B5 | **System info** (battery, network, OS, uptime) | `psutil` + `platform` | `psutil` + `platform` (Win32 API) | `psutil` + `platform` (sysfs) | `psutil` | `pytest`: values present + typed; headless → graceful degradation |
| B6 | **Notifications from worker** | dispatch via CLIENT A4 bridge (NSUserNotification/UN) | bridge to toast | bridge to D-Bus | CLIENT notification plugin | integration: worker request → client notification observed; no notification daemon → typed unsupported |
| B7 | **Computer-use: screen capture** (P2) | Screen Recording TCC permission; CGDisplayStream / `screencapture` | `BitBlt`/Windows.Graphics.Capture (requires consent + focus) | X11 `XGetImage` / Wayland portal (limited, per-window) | platform APIs + permission prompts | e2e: capture desktop, assert image; permission denied → typed error, no fallback |
| B8 | **Computer-use: input simulation** (P2) | CGEvent via Accessibility (TCC) | `SendInput` | X11 XTest / Wayland portal (restricted) | platform APIs + accessibility permissions | e2e: move+click on test target, assert event; denied → typed error |

## C. Core backend — platform-independent (CORE, runs everywhere)

| # | Capability | Impl | Deps | Verification test |
|---|-----------|------|------|-------------------|
| C1 | **Auth / pairing** (OIDC, device flow, API keys) | FastAPI + authlib | `authlib`, `pydantic-settings` | `pytest`: token issuance, device-flow pairing, key revocation |
| C2 | **Agent orchestration** | async orchestrator, session/plan state | FastAPI, Pydantic | `pytest`: end-to-end tool-call loop with mocked provider |
| C3 | **Memory** | Postgres (Hybrid/Remote) or SQLite (Local) via SQLAlchemy | `sqlalchemy`, `aiosqlite`, `asyncpg` | `pytest`: CRUD, scoping, TTL; both engines |
| C4 | **Task state** (durable jobs, retries) | state machine + job store | same as C3 | `pytest`: retry, cancel, crash-recovery |
| C5 | **Policies & audit log** | policy engine + append-only audit table | — | `pytest`: policy denies, audit row written for every op |
| C6 | **Workflow scheduling** | Local: in-process scheduler; Hybrid/Remote: n8n | `apscheduler` (local) | `pytest`: schedule fires; n8n bridge mocked |
| C7 | **Provider abstraction** (LLM/STT/TTS/data) | interface + registry, config-driven selection | provider SDKs behind interface | `pytest`: registry swap, config-driven default |

## D. Cross-cutting portability requirements (all layers)

| # | Requirement | Where enforced | Test |
|---|-------------|----------------|------|
| D1 | No hardcoded home dirs / usernames / exe paths | `platformdirs` + config layer (`pydantic-settings`); env overrides | `pytest`: run suite with `HOME`/`USERPROFILE`/`XDG_*` overridden → paths still resolve |
| D2 | Secrets never in source | env vars, OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service/keyring) via `keyring` | `pytest` with mocked keyring: secret round-trip, no literal in repo scan |
| D3 | Core logic OS-independent | CI runs backend tests on macOS, Windows, Linux runners | CI matrix job must pass on all three |
| D4 | DI + adapters for platform code | `PlatformAdapter` ABC (ADR-0003) injected via FastAPI `Depends` | `pytest`: fake adapter injected; real adapters import-test on each OS |
| D5 | Feature parity documentation | this matrix + client "capabilities" endpoint (`GET /api/capabilities`) | integration: advertised == matrix ∩ tested |

## E. Known limitations (first release)

- **Wayland** (Linux): global hotkeys and full screen capture need portal support
  and are not guaranteed; degrade to `UnsupportedCapability` with an explanation.
- **Windows**: long-path operations require the `\\?\` prefix and App-Loader
  awareness; covered by B2 test. Notification toasts need a Start Menu shortcut
  (packaging concern, not runtime).
- **macOS**: screen capture / input simulation require TCC approvals; on first
  use the client must show the system permission dialog. Microphone access on
  macOS needs an `NSMicrophoneUsageDescription` in `Info.plist`.
- **Wake word** is a native-binary dependency (Porcupine); packaged per-OS in CI.
  If the audio input is unavailable, the assistant degrades to manual/button
  trigger — never a polling workaround.
- **Headless servers** (deployment mode C): client-only capabilities (A1–A11)
  are unavailable; the web client operates in "no local machine access" mode.