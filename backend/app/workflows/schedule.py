"""Schedule primitives for the local in-process scheduler (matrix row C6).

Two schedule types, both described in a workflow definition's ``schedule`` key:

- ``{"type": "interval", "seconds": 3600}`` — fire every N seconds.
- ``{"type": "cron", "expression": "0 9 * * *"}`` — standard 5-field cron:
  minute(0-59) hour(0-23) day-of-month(1-31) month(1-12) day-of-week(0-6,
  0=Sunday). Each field supports ``*``, ``*/step``, ``a-b`` ranges and
  ``a,b,c`` lists.

Parsing is stdlib-only and deliberately minimal — this is the *local* half of
C6. Hybrid/Remote gets the full cron/scheduling engine inside n8n.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

_HORIZON_DAYS = 366 * 4  # bounded search; ~4 years is far beyond any practical job


@dataclass(frozen=True)
class Schedule:
    """A time rule; ``next_run(after)`` returns the first run strictly after ``after``."""

    def next_run(self, after: datetime) -> datetime:
        raise NotImplementedError


@dataclass(frozen=True)
class IntervalSchedule(Schedule):
    seconds: int

    def next_run(self, after: datetime) -> datetime:
        if self.seconds <= 0:
            raise ValueError("interval seconds must be positive")
        return after + timedelta(seconds=self.seconds)


@dataclass(frozen=True)
class CronSchedule(Schedule):
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]

    @classmethod
    def parse(cls, expression: str) -> CronSchedule:
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"cron expression must have 5 fields, got {len(fields)}: {expression!r}"
            )
        minutes = _parse_field(fields[0], 0, 59)
        hours = _parse_field(fields[1], 0, 23)
        days_of_month = _parse_field(fields[2], 1, 31)
        months = _parse_field(fields[3], 1, 12)
        days_of_week = _parse_field(fields[4], 0, 6)
        if not (minutes and hours and days_of_month and months and days_of_week):
            raise ValueError(f"cron field has no allowed values: {expression!r}")
        return cls(minutes, hours, days_of_month, months, days_of_week)

    def next_run(self, after: datetime) -> datetime:
        """First valid minute strictly after ``after`` (UTC), or raise."""
        for offset in range(_HORIZON_DAYS + 1):
            day = (after.date() + timedelta(days=offset))
            if day.month not in self.months:
                continue
            if day.day not in self.days_of_month:
                continue
            # cron day-of-week: 0=Sunday … 6=Saturday; datetime.weekday(): 0=Mon.
            if ((day.weekday() + 1) % 7) not in self.days_of_week:
                continue
            for hour in sorted(self.hours):
                if offset == 0 and hour < after.hour:
                    continue
                for minute in sorted(self.minutes):
                    same_minute = offset == 0 and hour == after.hour
                    if same_minute and minute <= after.minute:
                        continue
                    return datetime.combine(day, time(hour, minute), tzinfo=UTC)
        raise ValueError(f"no run scheduled within {_HORIZON_DAYS} days of {after.isoformat()}")


def _parse_field(raw: str, lo: int, hi: int) -> frozenset[int]:
    """Parse one cron field (``*``, ``*/n``, ``a-b``, ``a,b``) into a value set."""
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            base, _, step_raw = part.partition("/")
            step = max(1, int(step_raw))
            if base in ("*", "?"):
                base_lo, base_hi = lo, hi
            else:
                if "-" in base:
                    a, b = (int(x) for x in base.split("-", 1))
                else:
                    a = b = int(base)
                base_lo, base_hi = a, b
            out.update(v for v in range(base_lo, base_hi + 1) if (v - base_lo) % step == 0)
            continue
        if part == "?":
            out.update(range(lo, hi + 1))
            continue
        if part == "*":
            out.update(range(lo, hi + 1))
            continue
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            out.update(range(a, b + 1))
            continue
        out.add(int(part))
    return frozenset(v for v in out if lo <= v <= hi)


def parse_schedule(raw: dict) -> Schedule:
    """Validate a workflow definition's ``schedule`` mapping."""
    if not isinstance(raw, dict):
        raise TypeError("schedule must be an object")
    kind = raw.get("type")
    if kind == "interval":
        seconds = raw.get("seconds")
        if not isinstance(seconds, int) or seconds <= 0:
            raise ValueError("interval schedule requires a positive integer 'seconds'")
        return IntervalSchedule(seconds)
    if kind == "cron":
        expression = raw.get("expression")
        if not isinstance(expression, str):
            raise ValueError("cron schedule requires a 'expression' string")
        return CronSchedule.parse(expression)
    raise ValueError(f"unknown schedule type: {kind!r}")