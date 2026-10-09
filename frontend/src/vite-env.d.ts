/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL, e.g. http://127.0.0.1:8000 (default). */
  readonly VITE_JARVIS_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Present when running inside the Tauri shell (vs. a plain browser). */
declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export {};