"""Local in-process scheduler tests (matrix row C6 — Local half).

Covers the pure schedule primitives (interval + cron), the JSON workflow
definition loader (validation, default-deny of broken files), and the
provider behaviour end-to-end:

- ``list_workflows()`` / ``health()`` reflect definitions and thread state.
- ``run_workflow()`` runs steps through the bound agent executor (policy +
  audit) with ``{{input.*}}`` payload interpolation.
- The tick thread fires a scheduled workflow and audits every step.
- Policy-denied steps are audited, not executed (no allowlist bypass).
- A scheduler without a runner degrades gracefully instead of crashing.
"""
from __future__ import annotations

import json
import time

import pytest

from app.workflows.base import WorkflowUnavailable
from app.workflows.local import LocalSchedulerWorkflowProvider
from app.workflows.schedule import CronSchedule, IntervalSchedule, parse_schedule


def write_workflow(dir_path, wf: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{wf['id']}.json").write_text(
        json.dumps(wf), encoding="utf-8"
    )


# --- schedule primitives ----------------------------------------------------


def test_interval_next_run_adds_seconds():
    s = IntervalSchedule(seconds=90)
    from datetime import UTC, datetime

    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert s.next_run(now) == datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC)


def test_interval_rejects_non_positive():
    with pytest.raises(ValueError):
        IntervalSchedule(seconds=0).next_run(_utc(2026, 1, 1))


def _utc(y, m, d, hh=0, mm=0):
    from datetime import UTC, datetime

    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_cron_every_day_at_0900():
    s = CronSchedule.parse("0 9 * * *")
    assert s.next_run(_utc(2026, 1, 1, 8, 59)) == _utc(2026, 1, 1, 9, 0)
    assert s.next_run(_utc(2026, 1, 1, 9, 0)) == _utc(2026, 1, 2, 9, 0)  # strictly after


def test_cron_rolls_over_month_end():
    s = CronSchedule.parse("30 23 * * *")
    assert s.next_run(_utc(2026, 1, 31, 22, 0)) == _utc(2026, 1, 31, 23, 30)


def test_cron_dow_filter():
    # 2026-01-01 is a Thursday (weekday 3). "0 9 * * 1" = Mondays.
    s = CronSchedule.parse("0 9 * * 1")
    assert s.next_run(_utc(2026, 1, 1)) == _utc(2026, 1, 5, 9, 0)


def test_cron_step_and_range_fields():
    s = CronSchedule.parse("*/15 9-17 * * 1-5")
    assert s.next_run(_utc(2026, 1, 1, 8, 0)) == _utc(2026, 1, 1, 9, 0)  # first * /15 in hour 9
    assert 9 in s.hours and 17 in s.hours
    assert s.minutes == frozenset({0, 15, 30, 45})


def test_cron_bad_expression_rejected():
    with pytest.raises(ValueError):
        CronSchedule.parse("not a cron")
    with pytest.raises(ValueError):
        CronSchedule.parse("60 * * * *")  # minute 60 out of range


def test_parse_schedule_dispatch():
    assert isinstance(parse_schedule({"type": "interval", "seconds": 5}), IntervalSchedule)
    assert isinstance(parse_schedule({"type": "cron", "expression": "* * * * *"}), CronSchedule)
    with pytest.raises(ValueError):
        parse_schedule({"type": "bogus"})
    with pytest.raises(TypeError):
        parse_schedule("interval")  # not a dict


# --- definition loading -----------------------------------------------------


def test_loads_valid_definitions(tmp_path):
    write_workflow(tmp_path, {
        "id": "daily-report",
        "name": "Daily report",
        "schedule": {"type": "interval", "seconds": 60},
        "steps": [{"tool": "memory.store", "args": {"fact": "ran"}}],
    })
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    rows = provider.list_workflows()
    assert rows[0]["id"] == "daily-report"
    assert rows[0]["schedule"] == {"type": "interval", "seconds": 60}
    assert rows[0]["steps"] == ["memory.store"]


def test_invalid_file_skipped_gracefully(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    write_workflow(tmp_path, {
        "id": "ok",
        "schedule": {"type": "interval", "seconds": 60},
        "steps": [{"tool": "memory.store"}],
    })
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    assert [w["id"] for w in provider.list_workflows()] == ["ok"]
    assert provider.health()["total"] == 1


def test_missing_dir_is_empty_not_error(tmp_path):
    provider = LocalSchedulerWorkflowProvider(tmp_path / "nope")
    assert provider.list_workflows() == []
    assert provider.health()["total"] == 0


def test_validation_rejects_bad_definition(tmp_path):
    write_workflow(tmp_path, {"id": "no-steps", "schedule": {"type": "interval", "seconds": 10}})
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    assert provider.list_workflows() == []
    assert "no-steps" in (provider.health().get("last_error") or "")


# --- execution --------------------------------------------------------------


class _RecordingRunner:
    """Stand-in for the agent executor: records calls, applies policy for shell."""

    def __init__(self, allow: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.allow = allow or set()

    def __call__(self, name: str, args: dict):
        self.calls.append((name, args))
        if name == "shell.run" and args["command"].split()[0] not in self.allow:
            return "Denied by policy: not allowlisted"
        return "ok"


def test_run_workflow_interpolates_payload(tmp_path):
    write_workflow(tmp_path, {
        "id": "report",
        "schedule": {"type": "interval", "seconds": 60},
        "steps": [
            {"tool": "memory.store", "args": {"fact": "ran for {{input.who}}"}},
            {"tool": "shell.run", "args": {"command": "echo {{input.chore}}"}},
        ],
    })
    runner = _RecordingRunner(allow={"echo"})
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    provider.bind_step_runner(runner)
    result = provider.run_workflow("report", {"who": "alice", "chore": "tidy-up"})
    assert result["workflow"] == "report"
    assert runner.calls == [
        ("memory.store", {"fact": "ran for alice"}),
        ("shell.run", {"command": "echo tidy-up"}),
    ]
    assert [s["outcome"] for s in result["steps"]] == ["ok", "ok"]


def test_run_workflow_unknown_id_raises_unavailable(tmp_path):
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    with pytest.raises(WorkflowUnavailable, match="no workflow named"):
        provider.run_workflow("nope", {})


def test_run_workflow_without_runner_degrades(tmp_path):
    write_workflow(tmp_path, {
        "id": "job",
        "schedule": {"type": "interval", "seconds": 60},
        "steps": [{"tool": "memory.store"}],
    })
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    with pytest.raises(WorkflowUnavailable, match="not connected"):
        provider.run_workflow("job", {})


def test_run_incurs_policy_denied_step_keeps_outcome(tmp_path):
    write_workflow(tmp_path, {
        "id": "risky",
        "schedule": {"type": "interval", "seconds": 60},
        "steps": [{"tool": "shell.run", "args": {"command": "rm -rf /"}}],
    })
    runner = _RecordingRunner(allow=set())
    provider = LocalSchedulerWorkflowProvider(tmp_path)
    provider.bind_step_runner(runner)
    result = provider.run_workflow("risky", {})
    assert "Denied by policy" in result["steps"][0]["outcome"]


# --- tick thread ------------------------------------------------------------


def test_tick_runs_due_workflow_and_schedules_next(tmp_path):
    write_workflow(tmp_path, {
        "id": "every-sec",
        "schedule": {"type": "interval", "seconds": 1},
        "steps": [{"tool": "memory.store", "args": {"fact": "tick"}}],
    })
    runner = _RecordingRunner()
    provider = LocalSchedulerWorkflowProvider(tmp_path, tick_seconds=0.05)
    provider.bind_step_runner(runner)
    provider.start()
    try:
        deadline = time.monotonic() + 5
        while not runner.calls and time.monotonic() < deadline:
            time.sleep(0.05)
        assert runner.calls, "scheduled job never fired"
        assert runner.calls[0] == ("memory.store", {"fact": "tick"})
        assert provider.health()["scheduler_thread"] is True
    finally:
        provider.stop()


def test_tick_audits_steps_via_runner_order(tmp_path):
    write_workflow(tmp_path, {
        "id": "two-step",
        "schedule": {"type": "interval", "seconds": 1},
        "steps": [
            {"tool": "memory.store", "args": {"fact": "one"}},
            {"tool": "memory.store", "args": {"fact": "two"}},
        ],
    })
    runner = _RecordingRunner()
    provider = LocalSchedulerWorkflowProvider(tmp_path, tick_seconds=0.05)
    provider.bind_step_runner(runner)
    provider.start()
    try:
        deadline = time.monotonic() + 5
        while len(runner.calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert [c[1]["fact"] for c in runner.calls[:2]] == ["one", "two"]
    finally:
        provider.stop()


def test_tick_honours_list_workflows_contract(tmp_path):
    write_workflow(tmp_path, {
        "id": "disabled",
        "enabled": False,
        "schedule": {"type": "interval", "seconds": 1},
        "steps": [{"tool": "memory.store", "args": {"fact": "never"}}],
    })
    runner = _RecordingRunner()
    provider = LocalSchedulerWorkflowProvider(tmp_path, tick_seconds=0.05)
    provider.bind_step_runner(runner)
    provider.start()
    try:
        time.sleep(0.3)  # a couple of ticks
        assert runner.calls == []  # disabled workflow never fires
        assert provider.health()["enabled"] == 0
    finally:
        provider.stop()