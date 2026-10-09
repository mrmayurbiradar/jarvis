"""Approved tools exposed to the agent (tool layer).

Each tool is a plain spec + callable that uses the injected context
(adapter, store, settings). Policy and audit are applied by the agent
orchestrator, not here.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.policies import PolicyDenied, ShellPolicy
from app.core.store import Store
from app.execution.platform.base import PlatformAdapter
from app.workflows.base import WorkflowProvider, WorkflowUnavailable


@dataclass
class ToolContext:
    adapter: PlatformAdapter
    store: Store
    allowlist_commands: frozenset[str]
    allowlist_apps: frozenset[str]
    workflow: WorkflowProvider | None = None
    allowlist_webhooks: frozenset[str] = frozenset()
    mcp: Any = None  # McpToolBridge, lazily imported to avoid import cycles


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    requires_approval: bool = False
    policy: Callable[[dict[str, Any]], None] | None = None
    run: Callable[[ToolContext, dict[str, Any]], str] | None = None


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _run_shell(ctx: ToolContext, args: dict[str, Any]) -> str:
    result = ctx.adapter.run_shell(args["command"], timeout=30.0)
    return (
        f"exit_code={result.exit_code}\n"
        f"stdout={result.stdout.strip()}\n"
        f"stderr={result.stderr.strip()}"
    )


def _launch_app(ctx: ToolContext, args: dict[str, Any]) -> str:
    pid = ctx.adapter.launch_application(args["target"])
    return f"launched (pid={pid})"


def _system_info(ctx: ToolContext, args: dict[str, Any]) -> str:
    return _json(ctx.adapter.system_info().__dict__)


def _memory_store(ctx: ToolContext, args: dict[str, Any]) -> str:
    ctx.store.save_memory(args["session_id"], args["fact"])
    return "stored"


def _memory_recall(ctx: ToolContext, args: dict[str, Any]) -> str:
    rows = ctx.store.recall_memory(args["query"], limit=5)
    return _json(rows)


def _workflow_list(ctx: ToolContext, args: dict[str, Any]) -> str:
    if ctx.workflow is None:
        return "Unavailable: workflow layer not configured (set JARVIS_N8N_BASE_URL)."
    try:
        rows = ctx.workflow.list_workflows()
    except WorkflowUnavailable as exc:
        return f"Workflow unavailable: {exc.reason}"
    return _json(rows)


def _workflow_run(ctx: ToolContext, args: dict[str, Any]) -> str:
    if ctx.workflow is None:
        return "Unavailable: workflow layer not configured (set JARVIS_N8N_BASE_URL)."
    try:
        result = ctx.workflow.run_workflow(args["webhook"], args.get("input") or {})
    except WorkflowUnavailable as exc:
        return f"Workflow unavailable: {exc.reason}"
    return _json(result)


def _require_in(target: str, allowlist: frozenset[str], what: str) -> None:
    if target not in allowlist:
        raise PolicyDenied(f"target not allowlisted for {what}: {target!r}")


def build_tools(ctx: ToolContext) -> list[ToolSpec]:
    tools: list[ToolSpec] = [
        ToolSpec(
            name="shell.run",
            description="Run an approved shell command on the user's machine.",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            requires_approval=True,
            policy=lambda args: ShellPolicy(
                allowed_executables=ctx.allowlist_commands
            ).check(args["command"]),
            run=_run_shell,
        ),
        ToolSpec(
            name="app.launch",
            description="Open an application, URL or file with the OS default handler.",
            parameters={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
            policy=lambda args: _require_in(args["target"], ctx.allowlist_apps, "app.launch"),
            run=_launch_app,
        ),
        ToolSpec(
            name="system.info",
            description="Read basic system information (OS, CPU, memory).",
            parameters={"type": "object", "properties": {}},
            run=_system_info,
        ),
        ToolSpec(
            name="memory.store",
            description="Store a fact about the user or project in long-term memory.",
            parameters={
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
            run=_memory_store,
        ),
        ToolSpec(
            name="memory.recall",
            description="Search stored memories.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            run=_memory_recall,
        ),
        ToolSpec(
            name="workflow.list",
            description="List workflows available on the connected automation engine.",
            parameters={"type": "object", "properties": {}},
            run=_workflow_list,
        ),
        ToolSpec(
            name="workflow.run",
            description=(
                "Run a workflow by its webhook trigger path on the automation engine "
                "(n8n). Executes real automations — only allowlisted webhooks run, "
                "and this tool requires human approval when JARVIS_REQUIRE_APPROVAL=1."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "webhook": {
                        "type": "string",
                        "description": "n8n webhook trigger path, e.g. daily-report",
                    },
                    "input": {
                        "type": "object",
                        "description": "JSON payload to pass to the workflow",
                    },
                },
                "required": ["webhook"],
            },
            requires_approval=True,
            policy=lambda args: _require_in(
                args["webhook"], ctx.allowlist_webhooks, "workflow.run"
            ),
            run=_workflow_run,
        ),
    ]
    # MCP tool servers (Layer 4): bridge their advertised tools into the agent.
    if ctx.mcp is not None:
        tools.extend(ctx.mcp.build_tool_specs())
    return tools