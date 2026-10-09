/**
 * Worker-token persistence.
 *
 * Browser scaffold: localStorage. In the desktop shell this will move to the
 * OS keychain (matrix row D2) via Tauri IPC; the interface stays the same.
 */
const KEY = "jarvis.worker.token";

export function loadToken(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string): void {
  try {
    localStorage.setItem(KEY, token);
  } catch {
    /* storage unavailable — token lives only for this session */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* no-op */
  }
}