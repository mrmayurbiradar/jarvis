# ADR-0001: Tauri (v2) for the desktop client

- **Status:** Accepted
- **Date:** 2026-10 (baseline decision)
- **Owner:** Client layer

## Context

JARVIS needs a cross-platform desktop client for macOS (first), Windows 10/11 and
Linux, sharing a frontend with a future browser client. The client owns
client-side OS capabilities: microphone, wake word, notifications, tray,
autostart, clipboard, global hotkeys. The spec requires the choice be made
explicitly and not force a rewrite later.

## Options considered

| | Tauri 2 | Electron |
|---|---|---|
| Runtime | System webview (WKWebView / WebView2 / WebKitGTK) + Rust core | Bundled Chromium + Node.js |
| Binary size | ~5–15 MB | ~100 MB+ |
| Memory footprint | Low (single system webview) | High (full Chromium + Node) |
| Local OS access | Rust + official plugins (`notification`, `shell`, `clipboard-manager`, `dialog`, `fs`, `autostart`, `global-shortcut`, `single-instance`, `updater`, `deep-link`) | Node APIs + npm ecosystem |
| Web tech | Same frontend works in Tauri and in a plain browser | Same frontend works in Electron and browser |
| Language for host | Rust (memory-safe, strong types for a privileged local component) | JavaScript/TypeScript |
| Maturity | Stable since Oct 2024; large ecosystem, still younger than Electron | Very mature, 10+ years |
| Packaging | per-OS: dmg / NSIS-MSIX / AppImage+deb | electron-builder (dmg/nsis/AppImage) |

## Decision

Use **Tauri 2** for the desktop shell, with the shared React/TypeScript frontend.

Rationale:

1. **Resource profile.** JARVIS is an always-running background agent (tray,
   wake word). Electron's ~100 MB binary + full Chromium footprint is a poor fit
   for a resident assistant; Tauri's system-webview + small Rust core is a good one.
2. **Security posture.** The client is a privileged component (it can read the
   mic, open apps, read the clipboard). A small, memory-safe Rust core with
   per-capability allowlists (Tauri 2's `capabilities/` permission model) is a
   better trust boundary than a full Node runtime with `require` access.
3. **Shared frontend.** Tauri 2 hosts an ordinary web frontend, so the exact same
   bundle also runs in the browser client for deployment mode C — no dual
   implementation.
4. **Per-capability degradation** (the spec's hard requirement) maps cleanly onto
   Tauri commands returning a typed `UnsupportedCapability` when the underlying
   plugin/platform feature is absent.

### Consequences / mitigations

- **Rust toolchain** is required for desktop development — CI must provision it.
  Mitigation: backend, web client, and core logic are all platform-independent;
  Rust is confined to `apps/desktop`.
- **WebView2** must be present on Windows 10/11 (preinstalled on Win11, evergreen
  bootstrap for Win10). Mitigation: packaging step installs it if absent.
- **Linux** needs WebKitGTK and the usual GTK dev libs; Wayland lacks global
  hotkey/portal support in places → must degrade gracefully (matrix rows A8/B7).
- **Wake word** uses a native lib (Porcupine) — packaged per-OS, with manual
  trigger fallback (A6).
- **Verification at implementation time:** pin exact plugin versions and re-check
  the WebView2/WebKitGTK minimums before the first release.

## Alternatives rejected

- **Electron**: ruled out on size/RAM and on the security boundary argument.
  Acceptable later only as a measured fallback if Tauri proves insufficient for
  a needed OS capability.
- **Native (Swift/WinUI/GTK)**: no shared frontend; violates "shared frontend
  wherever practical".

## Links

- Portability matrix A1–A11 (client shell capabilities)
- ADR-0003 (OS abstraction boundary)
- Repository layout `apps/desktop/`