# JARVIS web client (deployment mode C)

Browser-based access to the platform. This is the **same shared frontend** as the
desktop app (`frontend/`), built as a plain web bundle — no Tauri runtime.

- `npm run build` → `dist/` (from `frontend/src`)
- `npm run preview` → serve it locally
- Point it at a backend with `VITE_JARVIS_API` (default `http://127.0.0.1:8000`).

In a browser, native client capabilities (wake word, clipboard, notifications,
autostart, hotkeys) are **unavailable by design** — the "This computer" panel
degrades gracefully instead of pretending (portability matrix, deployment mode C).
Local computer control still requires a separately paired + authorized local
worker (ADR-0005); the web client alone has no local machine access.