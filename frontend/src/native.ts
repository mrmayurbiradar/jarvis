/**
 * Native (client-shell) capability surface.
 *
 * Inside the Tauri shell these map to Rust commands (matrix A1–A11) returning
 * `CommandResult` (Ok | UnsupportedCapability | Failure). In a plain browser
 * there is no Tauri runtime, so every capability reports `Unsupported` — the
 * UI must degrade gracefully, never assume.
 */
export interface CommandResult {
  status: "ok" | "unsupported" | "failed";
  value?: string;
  capability?: string;
  reason?: string;
  code?: string;
  message?: string;
}

export interface NativeCapabilities {
  notifications: boolean;
  clipboard: boolean;
  autostart: boolean;
  wake_word: boolean;
  global_hotkey: boolean;
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
    __TAURI__?: {
      core?: {
        invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
      };
    };
  }
}

/** True when running inside the Tauri shell. */
export const inTauri = (): boolean =>
  typeof window !== "undefined" && (window.__TAURI_INTERNALS__ !== undefined || window.__TAURI__ !== undefined);

async function invoke(cmd: string, args: Record<string, unknown> = {}): Promise<CommandResult> {
  const tauri = window.__TAURI__;
  if (!inTauri() || !tauri?.core?.invoke) {
    return { status: "unsupported", capability: cmd, reason: "not running inside the Tauri shell" };
  }
  try {
    const raw = (await tauri.core.invoke(cmd, args)) as CommandResult;
    return raw;
  } catch (e) {
    return { status: "failed", code: cmd, message: String(e) };
  }
}

/** Runtime probe of which client capabilities actually exist (matrix A1–A11). */
export async function probeNativeCapabilities(): Promise<NativeCapabilities> {
  const [notifications, clipboard, autostart, wake_word, global_hotkey] = await Promise.all([
    invoke("capability_probe", { name: "notifications" }),
    invoke("capability_probe", { name: "clipboard" }),
    invoke("capability_probe", { name: "autostart" }),
    invoke("capability_probe", { name: "wake_word" }),
    invoke("capability_probe", { name: "global_hotkey" }),
  ]);
  return {
    notifications: notifications.status === "ok",
    clipboard: clipboard.status === "ok",
    autostart: autostart.status === "ok",
    wake_word: wake_word.status === "ok",
    global_hotkey: global_hotkey.status === "ok",
  };
}