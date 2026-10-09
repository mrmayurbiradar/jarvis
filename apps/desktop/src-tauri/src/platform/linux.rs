//! Linux implementation of the platform abstraction (see `mod.rs`).
//! Tries `xdg-open` then `gio open` — the same mechanism
//! `PlatformAdapter.linux` uses in the Python backend. If neither opener
//! exists we report `Unsupported` rather than falling back to something
//! dangerous (the no-dangerous-substitution rule from ADR-0002).

use super::CommandResult;

pub fn launch(target: &str) -> CommandResult {
    for opener in ["xdg-open", "gio"] {
        let mut cmd = std::process::Command::new(opener);
        if opener == "gio" {
            cmd.arg("open");
        }
        if let Ok(child) = cmd.arg(target).spawn() {
            return CommandResult::ok(format!("pid={}", child.id()));
        }
    }
    CommandResult::unsupported(
        "launch_application",
        "neither xdg-open nor gio is installed; refusing to substitute a fallback",
    )
}