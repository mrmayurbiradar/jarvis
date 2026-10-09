mod platform;

/// JARVIS desktop entry point. All platform work lives in `platform/`, which
/// mirrors the ADR-0003 `PlatformAdapter` contract from the Python backend:
/// every command returns a `CommandResult` with an explicit
/// `Ok | Unsupported | Failed` status so the UI can degrade gracefully instead
/// of crashing when a capability is missing on a given OS.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            platform::capability_probe,
            platform::launch_application,
            platform::notify,
            platform::clipboard_read,
            platform::clipboard_write,
            platform::autostart_enable,
            platform::autostart_disable,
            platform::autostart_enabled,
            platform::system_info,
        ])
        .run(tauri::generate_context!())
        .expect("error while running the JARVIS desktop shell");
}