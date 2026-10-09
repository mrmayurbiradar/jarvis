"""Daily briefing tool tests (app/tools/briefing.py) + morning-routine flow.

All external sources (gold API, FX, RSS feeds, weather) are monkeypatched so
the tests are hermetic; the real endpoints are exercised live on the running
backend.
"""
from __future__ import annotations

from unittest import mock

import pytest

from app.core.store import Store
from app.orchestration.agent import Agent
from app.providers.local import LocalAgentProvider
from app.tools import briefing
from app.tools.briefing import _briefing_now, _gold_line, _rss_headlines
from app.tools.registry import ToolContext

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>test</title>
<item><title>First headline</title></item>
<item><title>Second headline</title></item>
</channel></rss>"""


def fake_fetch(url: str, timeout: int = 15) -> str:
    if "gold-api" in url:
        return '{"price": 4195.8}'
    if "er-api" in url:
        return '{"rates": {"INR": 96.88}}'
    return RSS


@pytest.fixture
def ctx(tmp_path):
    from test_api import FakeAdapter

    store = Store(tmp_path / "briefing.db")
    store.create_task("todo", {"text": "ship the PR"}, status="open")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes").mkdir()
    return ToolContext(
        adapter=FakeAdapter(),
        store=store,
        allowlist_commands=frozenset(),
        allowlist_apps=frozenset(),
        workspace=workspace,
    )


def test_rss_headlines_parse():
    with mock.patch.object(briefing, "_fetch", fake_fetch):
        titles = _rss_headlines("https://news.ycombinator.com/rss", 2)
    assert titles == ["First headline", "Second headline"]


def test_rss_feed_failure_returns_empty_and_news_lines_degrade():
    with mock.patch.object(briefing, "_fetch", side_effect=OSError("no network")):
        lines = briefing._news_lines()
    assert lines and all("unavailable" in line for line in lines)


def test_gold_line_includes_inr_per_gram():
    with mock.patch.object(briefing, "_fetch", fake_fetch):
        line = _gold_line()
    # 4195.8 / 31.1034768 * 96.88 ≈ 13,069 INR/gram
    assert "₹13,069" in line
    assert "4,196" in line


def test_briefing_assembles_all_sections(ctx):
    with mock.patch.object(briefing, "_fetch", fake_fetch), mock.patch.object(
        briefing, "_weather", return_value="23°C, sunny"
    ):
        out = _briefing_now(ctx, {})
    assert "GOOD MORNING" in out
    assert "23°C" in out
    assert "gold:" in out
    assert "ship the PR" in out  # open task surfaced
    assert "First headline" in out  # RSS headlines surfaced
    assert "news" in out


def test_briefing_shows_notes_and_approvals(ctx):
    from datetime import datetime

    ctx.store.create_approval("sess", "shell.run", {"command": "echo x"})
    today = datetime.now().strftime("%Y-%m-%d")
    (ctx.workspace / "notes").joinpath(f"{today}.md").write_text(
        "- 09:00 standup call\n", encoding="utf-8"
    )
    with mock.patch.object(briefing, "_fetch", fake_fetch), mock.patch.object(
        briefing, "_weather", return_value="23°C, sunny"
    ):
        out = _briefing_now(ctx, {})
    assert "waiting for your approval" in out
    assert "standup call" in out


def test_briefing_now_never_crashes_when_sources_fail(ctx):
    with mock.patch.object(briefing, "_fetch", side_effect=OSError("down")), mock.patch.object(
        briefing, "_weather", side_effect=OSError("down")
    ):
        out = _briefing_now(ctx, {})
    assert "GOOD MORNING" in out
    assert "unavailable" in out


def test_start_my_day_routes_to_briefing_tool():
    provider = LocalAgentProvider()
    result = provider.complete([{"role": "user", "content": "start my day"}], [])
    assert result.tool_calls and result.tool_calls[0].name == "briefing.now"


def test_good_morning_routes_to_briefing_tool():
    provider = LocalAgentProvider()
    result = provider.complete([{"role": "user", "content": "good morning"}], [])
    assert result.tool_calls and result.tool_calls[0].name == "briefing.now"


def test_briefing_reply_passes_through(ctx):
    agent = Agent(llm=LocalAgentProvider(), ctx=ctx)
    with mock.patch.object(briefing, "_fetch", fake_fetch), mock.patch.object(
        briefing, "_weather", return_value="23°C, sunny"
    ):
        result = agent.run("s1", "start my day")
    assert "GOOD MORNING" in result.text
    assert result.tool_calls == 1