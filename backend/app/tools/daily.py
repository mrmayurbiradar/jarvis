"""Daily-work tools: tasks, notes, weather, workspace files.

These are the low-risk operations that make the agent useful for everyday
work — a to-do list, a dated journal, a no-key weather lookup, and a
workspace-scoped file viewer — and they work without a remote LLM (the
local provider routes plain-English requests to them).

Security posture (ADR-0005): none of these need approval. They are scoped
to their own store tables / the workspace directory, never to arbitrary
paths or destructive operations — the shell and launch tools remain the
only gated ones. Every call still lands in the append-only audit log via
the agent orchestrator.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from app.tools.registry import ToolContext, ToolSpec

NOTES_DIR = "notes"
MAX_READ_BYTES = 8192


# ---------------------------------------------------------------------------
# tasks (durable to-do list, stored in SQLite)
# ---------------------------------------------------------------------------

def _tasks_add(ctx: ToolContext, args: dict[str, Any]) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        return "error: no task text"
    row = ctx.store.create_task("todo", {"text": text}, status="open")
    return f'added "{text}" ({row["id"]})'


def _tasks_list(ctx: ToolContext, args: dict[str, Any]) -> str:
    rows = ctx.store.list_tasks(kind="todo", status="open")
    if not rows:
        return "No open tasks."
    lines = [f"{i}. {r['payload'].get('text', '')} ({r['id'][:8]})"
             for i, r in enumerate(rows, 1)]
    return "\n".join(lines)


def _tasks_done(ctx: ToolContext, args: dict[str, Any]) -> str:
    text = (args.get("text") or "").strip()
    task_id = (args.get("id") or "").strip()
    rows = ctx.store.list_tasks(kind="todo", status="open")
    if task_id:
        match = next((r for r in rows if r["id"].startswith(task_id)), None)
    elif text:
        match = next(
            (r for r in rows if r["payload"].get("text", "").lower().startswith(text.lower())),
            None,
        )
    else:
        match = None
    if match is None:
        return "not found: no open task matches"
    ctx.store.set_task_status(match["id"], "done")
    label = match["payload"].get("text", "")
    return f'done "{label}"'


# ---------------------------------------------------------------------------
# notes (dated journal, one markdown file per day under the workspace)
# ---------------------------------------------------------------------------

def _notes_path(workspace: Path) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    return workspace / NOTES_DIR / f"{day}.md"


def _notes_append(ctx: ToolContext, args: dict[str, Any]) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        return "error: no note text"
    path = _notes_path(ctx.workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H:%M")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} {text}\n")
    return f'saved ({path.name}): {text[:80]}'


def _notes_today(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _notes_path(ctx.workspace)
    if not path.exists():
        return "No notes yet today."
    with path.open(encoding="utf-8") as fh:
        return fh.read().strip() or "No notes yet today."


# ---------------------------------------------------------------------------
# weather (wttr.in — free, no API key)
# ---------------------------------------------------------------------------

def _weather(ctx: ToolContext, args: dict[str, Any]) -> str:
    location = (args.get("location") or "").strip()
    qs = f"?format=j1&{urllib.parse.urlencode({"lang": "en"})}"
    url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1" if location else "https://wttr.in/?format=j1"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cc = data["current_condition"][0]
        area = (data.get("nearest_area") or [{}])[0].get("areaName") or [{}]
        place = area[0].get("value", "")
        desc = (cc.get("weatherDesc") or [{}])[0].get("value", "—")
        temp = cc.get("temp_C", "?")
        suffix = f" in {place}" if place else ""
        return f"{temp}°C, {desc}{suffix}"
    except Exception as exc:  # noqa: BLE001 — network failures degrade gracefully
        return f"Weather unavailable: {exc}"


# ---------------------------------------------------------------------------
# workspace files (read-only, scoped to the workspace dir)
# ---------------------------------------------------------------------------

def _safe_path(workspace: Path, rel: str) -> Path | None:
    """Resolve rel under workspace; None if it escapes (no path traversal)."""
    base = workspace.resolve()
    try:
        p = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    if p == base or base in p.parents:
        return p
    return None


def _files_list(ctx: ToolContext, args: dict[str, Any]) -> str:
    rel = (args.get("dir") or "").strip()
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    target = _safe_path(ctx.workspace, rel) or ctx.workspace
    if not target.is_dir():
        return f"not a directory: {rel or '.'}"
    entries = []
    for child in sorted(target.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
        marker = "dir " if child.is_dir() else "file"
        entries.append(f"{marker} {child.name}")
    return "\n".join(entries) if entries else "(empty)"


def _files_read(ctx: ToolContext, args: dict[str, Any]) -> str:
    rel = (args.get("path") or "").strip()
    if not rel:
        return "error: no path"
    target = _safe_path(ctx.workspace, rel)
    if target is None:
        return "denied: outside workspace"
    if not target.is_file():
        return f"not a file: {rel}"
    try:
        with target.open(encoding="utf-8") as fh:
            content = fh.read(MAX_READ_BYTES)
    except UnicodeDecodeError:
        return f"(binary file, {target.stat().st_size} bytes)"
    if len(content) == MAX_READ_BYTES:
        content += "\n… (truncated)"
    return f"--- {rel} ---\n{content}"


# ---------------------------------------------------------------------------

def build_daily_tools(ctx: ToolContext) -> list[ToolSpec]:
    return [
        ToolSpec(
            name="tasks.add",
            description="Add a task to the user's to-do list.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The task to remember"}},
                "required": ["text"],
            },
            run=_tasks_add,
        ),
        ToolSpec(
            name="tasks.list",
            description="List the user's open to-do items.",
            parameters={"type": "object", "properties": {}},
            run=_tasks_list,
        ),
        ToolSpec(
            name="tasks.done",
            description="Mark a to-do item as done, by id or by its text.",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Task id prefix (optional)"},
                    "text": {"type": "string", "description": "Task text to match (optional)"},
                },
            },
            run=_tasks_done,
        ),
        ToolSpec(
            name="notes.append",
            description="Append a line to today's dated journal note.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            run=_notes_append,
        ),
        ToolSpec(
            name="notes.today",
            description="Read today's journal notes.",
            parameters={"type": "object", "properties": {}},
            run=_notes_today,
        ),
        ToolSpec(
            name="weather.now",
            description="Current weather for a location (no API key needed).",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or place (optional)"}
                },
            },
            run=_weather,
        ),
        ToolSpec(
            name="files.list",
            description="List files in the user's workspace directory.",
            parameters={
                "type": "object",
                "properties": {"dir": {"type": "string", "description": "Subdirectory (optional)"}},
            },
            run=_files_list,
        ),
        ToolSpec(
            name="files.read",
            description="Read a text file from the user's workspace directory.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            run=_files_read,
        ),
    ]