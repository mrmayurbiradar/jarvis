"""Tests for the keyless local agent brain (app/providers/local.py).

Routing: plain-English daily-work requests → tool calls / inline replies.
Reply composition: tool results → spoken-friendly text.
"""
from __future__ import annotations

import json

import pytest

from app.orchestration.agent import Agent
from app.providers.base import LlmResult
from app.providers.local import LocalAgentProvider
from app.tools.registry import ToolContext


def route(provider: LocalAgentProvider, text: str) -> LlmResult:
    return provider.complete([{"role": "user", "content": text}], tools=[])


def tool_args(result: LlmResult) -> dict:
    assert result.tool_calls, f"expected a tool call, got text={result.text!r}"
    return json.loads(result.tool_calls[0].arguments)


def test_greeting_returns_text_without_tools():
    result = route(LocalAgentProvider(), "Hello JARVIS")
    assert result.tool_calls == []
    assert "Hello" in result.text


def test_tasks_add_routes_and_extracts():
    result = route(LocalAgentProvider(), "add a task: buy groceries")
    assert result.tool_calls[0].name == "tasks.add"
    assert tool_args(result) == {"text": "buy groceries"}


def test_tasks_add_remind_me_to():
    result = route(LocalAgentProvider(), "remind me to call the dentist")
    assert result.tool_calls[0].name == "tasks.add"
    assert tool_args(result) == {"text": "call the dentist"}


def test_tasks_list_routes():
    result = route(LocalAgentProvider(), "what's my todo?")
    assert result.tool_calls[0].name == "tasks.list"


def test_tasks_done_by_text():
    result = route(LocalAgentProvider(), "mark buy groceries done")
    assert result.tool_calls[0].name == "tasks.done"
    assert tool_args(result) == {"text": "buy groceries"}


def test_tasks_done_by_id():
    result = route(LocalAgentProvider(), "task a1b2c3 done")
    assert result.tool_calls[0].name == "tasks.done"
    assert tool_args(result) == {"id": "a1b2c3"}


def test_notes_append():
    result = route(LocalAgentProvider(), "take a note: call Sam at 4")
    assert result.tool_calls[0].name == "notes.append"
    assert tool_args(result) == {"text": "call Sam at 4"}


def test_weather_routes_without_location():
    result = route(LocalAgentProvider(), "how's the weather?")
    assert result.tool_calls[0].name == "weather.now"


def test_weather_with_location():
    result = route(LocalAgentProvider(), "weather in Bengaluru")
    assert tool_args(result) == {"location": "Bengaluru"}


def test_now_returns_inline_text():
    result = route(LocalAgentProvider(), "what time is it?")
    assert result.tool_calls == []
    assert "It's" in result.text


def test_memory_store_route():
    result = route(LocalAgentProvider(), "remember that my desk is on the 4th floor")
    assert result.tool_calls[0].name == "memory.store"
    assert tool_args(result) == {"fact": "my desk is on the 4th floor"}


def test_files_read_routes():
    result = route(LocalAgentProvider(), "read README.md")
    assert result.tool_calls[0].name == "files.read"
    assert tool_args(result) == {"path": "README.md"}


def test_unknown_request_falls_back_to_help():
    result = route(LocalAgentProvider(), "tell me about quantum physics")
    assert result.tool_calls == []
    assert "add a task" in result.text  # help teaches the user what it can do


def test_tool_result_composes_reply():
    provider = LocalAgentProvider()
    result = provider.complete(
        [
            {"role": "user", "content": "what's my todo?"},
            {"role": "tool", "tool_call_id": "x", "name": "tasks.list",
             "content": "1. buy groceries (a1b2c3d4)"},
        ],
        tools=[],
    )
    assert "buy groceries" in result.text
    assert "to-do list" in result.text


def test_tasks_done_reply_wraps():
    provider = LocalAgentProvider()
    result = provider.complete(
        [
            {"role": "user", "content": "mark buy groceries done"},
            {"role": "tool", "tool_call_id": "x", "name": "tasks.done",
             "content": 'done "buy groceries"'},
        ],
        tools=[],
    )
    assert result.text == "Done — marked it complete."


@pytest.fixture
def agent_ctx(tmp_path):
    """Agent wired with the local provider, temp store and workspace."""
    from app.core.store import Store
    from app.execution.platform.base import PlatformAdapter, ShellResult, SystemInfo
    from app.execution.platform.base import UnsupportedCapability

    class FakeAdapter(PlatformAdapter):
        platform = "fake"

        @property
        def capabilities(self):
            return {"launch_application": False, "shell": True, "system_info": True}

        def default_shell(self):
            return "/bin/sh"

        def launch_application(self, target, *, wait=False):
            raise UnsupportedCapability("launch_application", "not in unit test")

        def run_shell(self, command, *, timeout=30.0):
            raise UnsupportedCapability("shell", "not in unit test")

        def system_info(self):
            return SystemInfo(os_name="fake", os_version="1", architecture="x86_64",
                              hostname="fake", cpu_count=1, memory_total_bytes=1024,
                              platform="fake")

    store = Store(tmp_path / "test.db")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# hello workspace\n", encoding="utf-8")
    ctx = ToolContext(
        adapter=FakeAdapter(),
        store=store,
        allowlist_commands=frozenset(),
        allowlist_apps=frozenset(),
        workspace=workspace,
    )
    return Agent(llm=LocalAgentProvider(), ctx=ctx)


def test_end_to_end_add_and_list(agent_ctx):
    r1 = agent_ctx.run("s1", "add a task: buy milk")
    assert "buy milk" in r1.text
    r2 = agent_ctx.run("s1", "what's my todo?")
    assert "buy milk" in r2.text
    r3 = agent_ctx.run("s1", "mark buy milk done")
    assert "marked" in r3.text.lower()
    r4 = agent_ctx.run("s1", "what's my todo?")
    assert "no open tasks" in r4.text.lower() or "clear" in r4.text.lower()


def test_end_to_end_notes(agent_ctx):
    r = agent_ctx.run("s1", "take a note: standup at 10")
    assert "saved" in r.text.lower()
    notes = agent_ctx.run("s1", "what did I note today?").text
    assert "standup at 10" in notes


def test_end_to_end_files_read_scoped(agent_ctx):
    out = agent_ctx.run("s1", "read README.md").text
    assert "hello workspace" in out
    denied = agent_ctx.run("s1", "read /etc/passwd").text
    assert "denied" in denied.lower() or "not a file" in denied.lower()