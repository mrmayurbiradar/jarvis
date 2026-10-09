"""Agent orchestration tests with a scripted LLM and fake adapter."""
from __future__ import annotations

from app.core.store import Store
from app.execution.platform.base import (
    PlatformAdapter,
    ShellResult,
    SystemInfo,
    UnsupportedCapability,
)
from app.orchestration.agent import Agent
from app.providers.base import LlmResult, ToolCall
from app.providers.mock import ScriptedLlmProvider
from app.tools.registry import ToolContext


class FakeAdapter(PlatformAdapter):
    platform = "fake"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"shell": True, "launch_application": False}

    def default_shell(self) -> str:
        return "sh"

    def launch_application(self, target: str, *, wait: bool = False) -> int:
        raise UnsupportedCapability("launch_application", "fake has no app launching")

    def run_shell(self, command: str, *, timeout: float | None = 30.0) -> ShellResult:
        return ShellResult(command=command, exit_code=0, stdout="ok", stderr="")

    def system_info(self) -> SystemInfo:
        return SystemInfo(
            os_name="fake", os_version="1", architecture="x", hostname="h",
            cpu_count=1, memory_total_bytes=1, platform=self.platform,
        )


def make_agent(
    store: Store,
    results: list[LlmResult],
    *,
    allowlist=("echo",),
    allowlist_apps=(),
    require_approval=False,
):
    ctx = ToolContext(
        adapter=FakeAdapter(),
        store=store,
        allowlist_commands=frozenset(allowlist),
        allowlist_apps=frozenset(allowlist_apps),
    )
    return Agent(
        llm=ScriptedLlmProvider(results),
        ctx=ctx,
        require_approval=require_approval,
    )


def _shell_call(command: str) -> ToolCall:
    return ToolCall(id="c1", name="shell.run", arguments=f'{{"command": "{command}"}}')


def _tool_outcome(result) -> str:
    """The last tool-message content from an agent run."""
    for msg in reversed(result.messages):
        if msg["role"] == "tool":
            return msg["content"]
    return ""


def test_agent_executes_tool_then_replies(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [LlmResult(tool_calls=[_shell_call("echo hi")]), LlmResult(text="done")],
    )
    result = agent.run("s1", "run echo hi")
    assert result.text == "done"
    assert result.tool_calls == 1
    # tool ran, then audit recorded allow/ok
    audit = store.list_audit()
    assert any(r["capability"] == "shell.run" and r["decision"] == "allow" for r in audit)


def test_agent_policy_denies_non_allowlisted(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [LlmResult(tool_calls=[_shell_call("rm -rf /")]), LlmResult(text="ok")],
    )
    result = agent.run("s1", "delete everything")
    assert "Denied by policy" in _tool_outcome(result)
    audit = store.list_audit()
    assert any(r["decision"] == "deny" and r["reason"].startswith("executable") for r in audit)


def test_agent_unknown_tool(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [LlmResult(tool_calls=[ToolCall(id="c", name="nope.run", arguments="{}")]), LlmResult(text="ok")],
    )
    result = agent.run("s1", "do something")
    assert "unknown tool" in _tool_outcome(result)


def test_agent_unsupported_capability_degrades_gracefully(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [
            LlmResult(tool_calls=[ToolCall(id="c", name="app.launch", arguments='{"target": "x"}')]),
            LlmResult(text="ok"),
        ],
        allowlist_apps=("x",),
    )
    result = agent.run("s1", "open x")
    assert "Unavailable on this platform" in _tool_outcome(result)


def test_agent_approval_gate_blocks_shell(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [LlmResult(tool_calls=[_shell_call("echo hi")]), LlmResult(text="ok")],
        require_approval=True,
    )
    result = agent.run("s1", "run echo")
    assert "Blocked: this action requires human approval" in _tool_outcome(result)
    audit = store.list_audit()
    assert any(r["outcome"] == "blocked" for r in audit)


def test_agent_memory_tools(tmp_path):
    store = Store(tmp_path / "test.db")
    agent = make_agent(
        store,
        [
            LlmResult(tool_calls=[ToolCall(id="c", name="memory.store", arguments='{"fact": "likes coffee"}')]),
            LlmResult(text="saved"),
        ],
    )
    result = agent.run("s1", "remember I like coffee")
    assert result.text == "saved"
    assert store.recall_memory("coffee")[0]["fact"] == "likes coffee"