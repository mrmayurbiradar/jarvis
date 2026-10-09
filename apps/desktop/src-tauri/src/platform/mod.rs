//! Platform abstraction for the JARVIS desktop shell.
//!
//! Mirrors the ADR-0003 `PlatformAdapter` contract from the Python backend:
//! every capability returns a [`CommandResult`] with an explicit
//! `Ok | Unsupported | Failed` status. A capability that does not exist on a
//! platform reports `Unsupported` with a reason — it is NEVER silently
//! substituted with a different, potentially dangerous command.
//!
//! Commands that plugins provide cross-platform (notification, clipboard,
//! autostart) are implemented once here. Commands that genuinely differ per
//! OS (launching applications) dispatch into per-OS modules.

use serde::Serialize;

/// The uniform result type returned to the frontend for every `invoke`.
/// Serialized with a `status` tag matching the `CommandResult` TS type in
/// `frontend/src/native.ts`.
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case", tag = "status")]
pub enum CommandResult {
    Ok { value: String },
    Unsupported { capability: String, reason: String },
    Failed { code: String, message: String },
}

impl CommandResult {
    pub fn ok(value: impl Into<String>) -> Self {
        CommandResult::Ok { value: value.into() }
    }

    pub fn unsupported(capability: &str, reason: impl Into<String>) -> Self {
        CommandResult::Unsupported {
            capability: capability.to_string(),
            reason: reason.into(),
        }
    }

    pub fn failed(code: &str, message: impl Into<String>) -> Self {
        CommandResult::Failed {
            code: code.to_string(),
            message: message.into(),
        }
    }
}

// --- Per-OS launch implementations ---------------------------------------

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "linux")]
mod linux;

/// Open `target` (a file, directory, or URL) with the OS default handler.
/// This is the one capability that genuinely needs per-OS code.
pub fn launch_application(target: &str) -> CommandResult {
    #[cfg(target_os = "macos")]
    {
        macos::launch(target)
    }
    #[cfg(target_os = "windows")]
    {
        windows::launch(target)
    }
    #[cfg(target_os = "linux")]
    {
        linux::launch(target)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        CommandResult::unsupported("launch_application", "no default-opener for this OS")
    }
}

// --- Cross-platform commands ---------------------------------------------

/// Probe whether a capability is available on this OS. The frontend calls this
/// at startup to render/disable UI accordingly (runtime capability detection
/// with graceful failure, per the architecture spec).
#[tauri::command]
pub fn capability_probe(name: String) -> CommandResult {
    match name.as_str() {
        // Provided by plugins registered in `lib.rs`:
        "notifications" => CommandResult::ok("available"),
        "clipboard" => CommandResult::ok("available"),
        "autostart" => CommandResult::ok("available"),
        // Not yet implemented anywhere (P2). Returning Unsupported here is what
        // lets the frontend show the Wake Word tab as disabled, not crash.
        "wake_word" => CommandResult::unsupported("wake_word", "not implemented (P2)"),
        "global_hotkey" => CommandResult::unsupported("global_hotkey", "not implemented (P2)"),
        other => CommandResult::unsupported(other, "unknown capability"),
    }
}

/// Launch an application/file/URL with the OS default handler.
#[tauri::command]
pub fn launch_application_command(target: String) -> CommandResult {
    launch_application(&target)
}

/// Send a desktop notification via the notification plugin.
#[tauri::command]
pub fn notify(app: tauri::AppHandle, title: String, body: String) -> CommandResult {
    use tauri_plugin_notification::NotificationExt;
    match app.notification().builder().title(title).body(body).show() {
        Ok(()) => CommandResult::ok("sent"),
        Err(e) => CommandResult::failed("notification", e.to_string()),
    }
}

/// Read the current clipboard text.
#[tauri::command]
pub fn clipboard_read(app: tauri::AppHandle) -> CommandResult {
    use tauri_plugin_clipboard_manager::ClipboardExt;
    match app.clipboard().read_text() {
        Ok(text) => CommandResult::ok(text),
        Err(e) => CommandResult::failed("clipboard", e.to_string()),
    }
}

/// Write text to the clipboard.
#[tauri::command]
pub fn clipboard_write(app: tauri::AppHandle, text: String) -> CommandResult {
    use tauri_plugin_clipboard_manager::ClipboardExt;
    match app.clipboard().write_text(text) {
        Ok(()) => CommandResult::ok("written"),
        Err(e) => CommandResult::failed("clipboard", e.to_string()),
    }
}

/// Enable "launch JARVIS at login" via the autostart plugin.
#[tauri::command]
pub fn autostart_enable(app: tauri::AppHandle) -> CommandResult {
    use tauri_plugin_autostart::ManagerExt;
    match app.autolaunch().enable() {
        Ok(()) => CommandResult::ok("enabled"),
        Err(e) => CommandResult::failed("autostart", e.to_string()),
    }
}

/// Disable "launch JARVIS at login".
#[tauri::command]
pub fn autostart_disable(app: tauri::AppHandle) -> CommandResult {
    use tauri_plugin_autostart::ManagerExt;
    match app.autolaunch().disable() {
        Ok(()) => CommandResult::ok("disabled"),
        Err(e) => CommandResult::failed("autostart", e.to_string()),
    }
}

/// Report whether autostart is currently enabled.
#[tauri::command]
pub fn autostart_enabled(app: tauri::AppHandle) -> CommandResult {
    use tauri_plugin_autostart::ManagerExt;
    match app.autolaunch().is_enabled() {
        Ok(v) => CommandResult::ok(if v { "true" } else { "false" }),
        Err(e) => CommandResult::failed("autostart", e.to_string()),
    }
}

/// Lightweight system info via `sysinfo` + Rust `consts`.
#[tauri::command]
pub fn system_info() -> CommandResult {
    let mut sys = sysinfo::System::new();
    sys.refresh_memory();
    let info = serde_json::json!({
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "host": std::env::consts::FAMILY,
        "cpus": sys.cpus().len(),
        "memory_total_bytes": sys.total_memory(),
        "memory_used_bytes": sys.used_memory(),
    });
    CommandResult::ok(info.to_string())
}