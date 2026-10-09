"""Local in-process workflow scheduler (matrix row C6 — Local half).

ADR-0004: Local-only mode uses an in-process scheduler instead of n8n so the
desktop client needs no containers. This provider implements the same
``WorkflowProvider`` interface as the n8n bridge — the backend, tools and API
do not know (or care) which engine is behind it:

- ``health()``          → scheduler thread status + enabled job count
- ``list_workflows()``  → the workflow definitions loaded from disk
- ``run_workflow()``    → run a workflow's steps immediately (webhook analogy)

Workflows are plain JSON files in ``JARVIS_WORKFLOWS_DIR`` (one workflow per
file, filenames are the ``id``), e.g. ``daily-report.json``::

    {
      "name": "Daily report",
      "description": "Collect system info and store a fact",
      "enabled": true,
      "schedule": {"type": "cron", "expression": "0 9 * * *"},
      "steps": [
        {"tool": "system.info", "args": {}},
        {"tool": "memory.store", "args": {"fact": "daily report ran"}}
      ]
    }

Each step invokes an approved agent tool *through the same policy → approval →
audit path as a chat request* (the step runner is the agent's tool executor),
so a scheduled automation can never bypass the allowlists or the audit log.
Manual ``run_workflow`` receives a payload that steps can interpolate via
``{{input.<key>}}`` in their string arguments.

The scheduler is a stdlib ``threading`` daemon — no new dependency, consistent
with the n8n bridge being urllib-only. It is deliberately simple: a tick thread
that wakes every ``tick_seconds`` and runs every workflow whose next run time
has passed. Hybrid/Remote gets the full scheduler inside n8n.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import WorkflowProvider, WorkflowUnavailable
from .schedule import Schedule, parse_schedule

log = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"\{\{\s*input\.([A-Za-z0-9_.]+)\s*\}\}")

#: Callable(step, args) -> outcome string. Injected by `create_app` so steps run
#: through the agent's tool executor (policy + approval + audit). A scheduler
#: without a bound runner can list/health but not execute.
StepRunner = Callable[[str, dict[str, Any]], str]


class LocalSchedulerWorkflowProvider(WorkflowProvider):
    def __init__(
        self,
        workflows_dir: str | Path,
        *,
        tick_seconds: float = 30.0,
        timezone: str = "UTC",
    ) -> None:
        self.workflows_dir = Path(workflows_dir)
        self.tick_seconds = tick_seconds
        self.timezone = timezone
        self._runner: StepRunner | None = None

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_run: dict[str, datetime] = {}  # workflow id -> next scheduled run
        self._last_error: str | None = None

    # --- lifecycle ----------------------------------------------------------

    def bind_step_runner(self, runner: StepRunner) -> None:
        """Attach the agent tool executor; makes scheduled steps executable."""
        self._runner = runner

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._tick_loop, name="jarvis-local-scheduler", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- WorkflowProvider interface -----------------------------------------

    def health(self) -> dict[str, Any]:
        try:
            workflows = self._load_workflows()
        except OSError as exc:
            raise WorkflowUnavailable(f"cannot read workflows dir: {exc}") from exc
        running = self._thread is not None and self._thread.is_alive()
        enabled = [w["id"] for w in workflows.values() if w["enabled"]]
        result: dict[str, Any] = {
            "status": "ok" if running else "idle",
            "engine": "local-scheduler",
            "scheduler_thread": running or self._stopped_reason(),
            "enabled": len(enabled),
            "total": len(workflows),
            "workflow_ids": list(workflows),
        }
        if self._last_error:
            result["last_error"] = self._last_error
        return result

    def list_workflows(self) -> list[dict[str, Any]]:
        try:
            workflows = self._load_workflows()
        except OSError as exc:
            raise WorkflowUnavailable(f"cannot read workflows dir: {exc}") from exc
        rows = []
        for wf in workflows.values():
            rows.append(
                {
                    "id": wf["id"],
                    "name": wf["name"],
                    "description": wf.get("description", ""),
                    "enabled": wf["enabled"],
                    "schedule": wf["schedule"],
                    "steps": [s["tool"] for s in wf["steps"]],
                }
            )
        return rows

    def run_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            workflows = self._load_workflows()
        except OSError as exc:
            raise WorkflowUnavailable(f"cannot read workflows dir: {exc}") from exc
        wf = workflows.get(workflow_id)
        if wf is None:
            raise WorkflowUnavailable(f"no workflow named {workflow_id!r}")
        if self._runner is None:
            raise WorkflowUnavailable("scheduler not connected to the agent tool executor")
        outcomes: list[dict[str, Any]] = []
        for step in wf["steps"]:
            tool = step["tool"]
            args = self._interpolate(step.get("args") or {}, payload)
            outcome = self._runner(tool, args)
            outcomes.append({"tool": tool, "outcome": outcome})
        return {"workflow": workflow_id, "name": wf["name"], "steps": outcomes}

    # --- internals ----------------------------------------------------------

    def _tick_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                self._last_error = str(exc)
                log.exception("local scheduler tick failed")
            self._stop.wait(self.tick_seconds)

    def _tick(self) -> None:
        try:
            workflows = self._load_workflows()
        except OSError as exc:
            self._last_error = str(exc)
            return
        now = datetime.now(UTC)
        for wf_id, wf in workflows.items():
            if not wf["enabled"]:
                continue
            schedule: Schedule = wf["_schedule"]
            next_run = self._next_run.get(wf_id)
            if next_run is None:
                try:
                    self._next_run[wf_id] = schedule.next_run(now)
                except ValueError as exc:  # no matches within horizon
                    self._last_error = f"{wf_id}: {exc}"
                continue
            if next_run <= now:
                try:
                    self.execute_workflow(wf_id, wf, _TICK_ACTOR)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = f"{wf_id}: {exc}"
                self._next_run[wf_id] = schedule.next_run(now)

    def execute_workflow(self, wf_id: str, wf: dict[str, Any], actor: str) -> dict[str, Any]:
        if self._runner is None:
            raise WorkflowUnavailable("scheduler not connected to the agent tool executor")
        outcomes: list[dict[str, Any]] = []
        for step in wf["steps"]:
            tool = step["tool"]
            args = self._interpolate(step.get("args") or {}, {})
            outcomes.append({"tool": tool, "outcome": self._runner(tool, args)})
        return {"workflow": wf_id, "name": wf["name"], "steps": outcomes}

    def _load_workflows(self) -> dict[str, dict[str, Any]]:
        """Load every ``*.json`` file in the workflows dir into a validated dict."""
        if not self.workflows_dir.is_dir():
            return {}
        workflows: dict[str, dict[str, Any]] = {}
        for path in sorted(self.workflows_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                wf = self._validate(raw)
            except (OSError, ValueError, TypeError) as exc:
                self._last_error = f"{path.name}: {exc}"
                log.warning("skipping invalid workflow %s: %s", path.name, exc)
                continue
            workflows[wf["id"]] = wf
        return workflows

    def _validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        wf_id = str(raw.get("id", "")).strip()
        if not wf_id:
            raise ValueError("workflow missing 'id'")
        name = str(raw.get("name", wf_id))
        steps = raw.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{wf_id}: 'steps' must be a non-empty list")
        for step in steps:
            if not isinstance(step, dict):
                raise TypeError(f"{wf_id}: each step must be an object")
            if not isinstance(step.get("tool"), str):
                raise TypeError(f"{wf_id}: each step's 'tool' must be a string")
        enabled = bool(raw.get("enabled", True))
        schedule = parse_schedule(raw.get("schedule") or {"type": "interval", "seconds": 3600})
        return {
            "id": wf_id,
            "name": name,
            "description": str(raw.get("description", "")),
            "enabled": enabled,
            "schedule": raw.get("schedule") or {"type": "interval", "seconds": 3600},
            "steps": steps,
            "_schedule": schedule,
        }

    def _interpolate(self, args: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """Replace ``{{input.<key>}}`` templates in string args with payload values."""

        def walk(value: Any) -> Any:
            if isinstance(value, str):
                return _TEMPLATE_RE.sub(lambda m: self._lookup(m.group(1), payload), value)
            if isinstance(value, dict):
                return {k: walk(v) for k, v in value.items()}
            if isinstance(value, list):
                return [walk(v) for v in value]
            return value

        return {k: walk(v) for k, v in args.items()}

    @staticmethod
    def _lookup(key: str, payload: dict[str, Any]) -> str:
        parts = key.split(".")
        value: Any = payload
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                return ""  # missing payload key → empty string, keeps the step safe
            value = value[part]
        try:
            return json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        except TypeError:
            return str(value)

    def _stopped_reason(self) -> str:
        return "stopped" if self._stop.is_set() else "not started"


#: Actor label for scheduled (ticker-driven) executions in the audit log.
_TICK_ACTOR = "scheduler"