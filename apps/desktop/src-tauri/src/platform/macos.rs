//! macOS implementation of the platform abstraction (see `mod.rs`).
//! Uses `open` to launch files/URLs/apps with the default handler — the
//! same mechanism `PlatformAdapter.macos` uses in the Python backend.

use super::CommandResult;

pub fn launch(target: &str) -> CommandResult {
    match std::process::Command::new("open").arg(target).spawn() {
        Ok(child) => CommandResult::ok(format!("pid={}", child.id())),
        Err(e) => CommandResult::failed("launch_application", e.to_string()),
    }
}