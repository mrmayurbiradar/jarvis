"""Daily briefing tool — the agent's morning routine (matrix row C2).

Compiles one spoken-ready morning digest, all keyless:
* date/time and the user's own state (open tasks, today's notes, pending
  approvals) straight from the store
* gold rate (gold-api.com) converted to INR per gram (open.er-api.com FX)
* headlines from RSS feeds — technology (HN), business/markets (BBC),
  politics (BBC), India business/tax (Economic Times)
* weather (wttr.in, shared with the daily tools)

Every external source degrades gracefully: a dead feed or API is skipped,
never a crash. Runs on demand from the agent brain ("start my day", "good
morning") and from the morning-briefing scheduled workflow.
"""
from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from app.tools.daily import _notes_today, _weather
from app.tools.registry import ToolContext, ToolSpec

GOLD_URL = "https://api.gold-api.com/price/XAU"
FX_URL = "https://open.er-api.com/v6/latest/USD"
GRAMS_PER_OUNCE = 31.1034768

# (label, rss url, max headlines). Order = display order.
NEWS_FEEDS: list[tuple[str, str, int]] = [
    ("technology", "https://news.ycombinator.com/rss", 3),
    ("business & markets", "https://feeds.bbci.co.uk/news/business/rss.xml", 3),
    ("politics", "https://feeds.bbci.co.uk/news/politics/rss.xml", 3),
    ("india business & tax", "https://economictimes.indiatimes.com/rssfeedsdefault.cms", 3),
]


def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _rss_headlines(url: str, count: int) -> list[str]:
    root = ET.fromstring(_fetch(url))
    titles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if title:
            titles.append(title)
        if len(titles) >= count:
            break
    return titles


def _gold_line() -> str:
    """USD/oz + INR per gram; each leg degrades independently."""
    usd = None
    try:
        data = json.loads(_fetch(GOLD_URL))
        usd = float(data["price"])
    except Exception as exc:  # noqa: BLE001
        return f"gold: unavailable ({exc})"
    grams_usd = usd / GRAMS_PER_OUNCE
    try:
        fx = json.loads(_fetch(FX_URL))
        inr = float(fx["rates"]["INR"])
        return f"gold: ${usd:,.0f}/oz · ₹{grams_usd * inr:,.0f} per gram (1 g ≈ ${grams_usd:,.0f})"
    except Exception as exc:  # noqa: BLE001
        return f"gold: ${usd:,.0f}/oz (INR rate unavailable: {exc})"


def _news_lines() -> list[str]:
    lines: list[str] = []
    for label, url, count in NEWS_FEEDS:
        try:
            titles = _rss_headlines(url, count)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{label}: unavailable ({exc})")
            continue
        if not titles:
            lines.append(f"{label}: no headlines right now")
            continue
        lines.append(f"{label}:\n" + "\n".join(f"  • {t}" for t in titles))
    return lines


def _briefing_now(ctx: ToolContext, args: dict[str, Any]) -> str:
    now = datetime.now().astimezone()
    lines = [f"GOOD MORNING — {now.strftime('%A, %B %-d, %-I:%M %p')}"]

    # weather (shared helper from the daily tools). Prefer an explicit
    # location arg, then the configured default city, then IP inference.
    try:
        loc = (args.get("location") or "").strip()
        default_city = getattr(ctx, "briefing_city", "") or ""
        loc = loc or default_city
        lines.append("weather: " + _weather(ctx, {"location": loc} if loc else {}))
    except Exception as exc:  # noqa: BLE001
        lines.append(f"weather: unavailable ({exc})")

    # gold
    lines.append(_gold_line())

    # user's own state from the store
    open_tasks = ctx.store.list_tasks(kind="todo", status="open")
    if open_tasks:
        lines.append("your open tasks:")
        lines.extend(f"  {i}. {r['payload'].get('text', '')}" for i, r in enumerate(open_tasks, 1))
    else:
        lines.append("your open tasks: none — clear slate")

    from app.tools.daily import _notes_today

    try:
        note_lines = _notes_today(ctx, {}).strip()
        if note_lines and not note_lines.startswith("No notes"):
            lines.append("notes so far today:\n" + "\n".join(f"  {n}" for n in note_lines.splitlines()))
    except Exception:  # noqa: BLE001
        pass

    pending = ctx.store.list_pending_approvals(limit=10)
    if pending:
        caps = ", ".join(sorted({p["capability"] for p in pending}))
        lines.append(f"{len(pending)} action(s) waiting for your approval ({caps}) — check the Approvals panel")

    # headlines
    lines.append("— news —")
    lines.extend(_news_lines())
    return "\n".join(lines)


def build_briefing_tool(ctx: ToolContext) -> ToolSpec:
    return ToolSpec(
        name="briefing.now",
        description=(
            "Compile the user's morning briefing: date/time, weather, gold rate, "
            "open tasks, today's notes, pending approvals, and headlines from "
            "technology, business/markets, politics and India business/tax feeds."
        ),
        parameters={
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City for weather (optional)"}},
        },
        run=_briefing_now,
    )