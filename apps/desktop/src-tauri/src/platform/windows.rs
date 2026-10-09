//! Windows implementation of the platform abstraction (see `mod.rs`).
//! Uses `cmd /c start` to open files/URLs/apps with the default handler —
//! the same mechanism `PlatformAdapter.windows` uses in the Python backend.

use super::CommandResult;

pub fn launch(target: &str) -> CommandResult {
    // `start` is a cmd builtin; the empty first arg is the window title.
    match std::process::Command::new("cmd")
        .args(["/c", "start", "", target])
        .spawn()
    {
        Ok(_) => CommandResult::ok("launched"),
        Err(e) => CommandResult::failed("launch_application", e.to_string()),
    }
}