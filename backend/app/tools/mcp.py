"""MCP tool bridge — spawn MCP servers and expose their tools to the agent.

Layer 4 of the architecture: *"MCP servers exposing approved tools … Each
tool is an independent process. Tools register with the backend; availability
is advertised at runtime."*

``McpToolBridge.build_tool_specs()`` returns one ``ToolSpec`` per advertised
MCP tool, named ``mcp.<server>.<tool>``. Calls proxy over stdio JSON-RPC to the
spawned server process. A server that fails to start, or a call that fails, is
surfaced as a *typed unavailable/error message back to the model* — never a
crash and never a silent skip (no-dangerous-substitution rule, ADR-0002).
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from typing import Any

from app.mcp.protocol import (
    encode_message,
    read_message,
)
from app.tools.registry import ToolSpec

log = logging.getLogger(__name__)


class McpUnavailable(Exception):
    """The MCP server process is unreachable or misconfigured."""


class McpClient:
    """Client for a single MCP server process (stdlib subprocess)."""

    def __init__(self, name: str, args: list[str], *, timeout: float = 15.0) -> None:
        self.name = name
        self.args = args
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def connect(self) -> list[dict[str, Any]]:
        """Start the process + handshake. Returns the server's advertised tools."""
        try:
            self._proc = subprocess.Popen(
                self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise McpUnavailable(f"cannot start {self.name}: {exc}") from exc
        init = self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "jarvis"}})
        if not init:
            raise McpUnavailable(f"{self.name}: initialize handshake failed")
        listed = self._rpc("tools/list", {}) or {}
        return listed.get("tools", []) if isinstance(listed, dict) else []

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return _extract_content(result)

    def _raw_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Like ``call`` but returns the raw result envelope (tests)."""
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise McpUnavailable(f"{self.name}: not connected")
        with self._lock:
            req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            try:
                proc.stdin.write(encode_message(req))
                proc.stdin.flush()
                resp = read_message(proc.stdout)
            except (OSError, ConnectionError) as exc:
                raise McpUnavailable(f"{self.name}: {method} failed: {exc}") from exc
            if resp is None:
                out = proc.stderr.read(500) if proc.stderr else b""
                raise McpUnavailable(f"{self.name}: connection closed during {method}: {(out or b'').decode(errors='ignore')}")
            if "error" in resp:
                raise McpUnavailable(f"{self.name}: {method} error: {resp['error']}")
            return resp.get("result")

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()


def mcp_arguments(server_name: str) -> tuple[str, ...]:
    """Invoke ``python -m app.mcp.servers.<server>`` from the backend tree."""
    return (sys.executable, "-m", f"app.mcp.servers.{server_name}")


def _extract_content(result: dict[str, Any]) -> dict[str, Any]:
    """Pull the model-facing payload out of an MCP ``tools/call`` result.

    MCP wraps tool output in ``{"content": [{"type": "text", "text": ...}]}``.
    The bridge hands the *text* to the agent (the model sees tool results as
    strings), and the server-side consumers get the raw dict back.
    """
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        text = "\n".join(
            str(b.get("text", "")) for b in result["content"] if isinstance(b, dict)
        )
        return {"text": text}
    return result


class McpToolBridge:
    """Owns the spawned MCP servers and produces agent ToolSpecs for them."""

    def __init__(self, spec: dict[str, Any] | None = None) -> None:
        spec = spec or {}
        self.clients: dict[str, McpClient] = {}
        self.tools: list[dict[str, Any]] = []
        self.unavailable: list[str] = []
        self.spec = spec

    def connect(self) -> None:
        for entry in self.spec.get("servers", []):
            name = entry.get("name")
            root = entry.get("root")
            if not name:
                continue
            args = mcp_arguments(name)
            if root:
                args += ("--root", str(root))
            client = McpClient(name=name, args=list(args))
            try:
                tools = client.connect()
            except McpUnavailable as exc:
                self.unavailable.append(str(exc))
                log.warning("mcp server %s unavailable: %s", name, exc)
                continue
            self.clients[name] = client
            for tool in tools or []:
                tool_name = tool.get("name")
                if tool_name:
                    self.tools.append({"server": name, "tool": tool})

    def close(self) -> None:
        for client in self.clients.values():
            client.close()
        self.clients.clear()

    def build_tool_specs(self) -> list[ToolSpec]:
        """Build agent ToolSpecs for each advertised MCP tool."""
        specs: list[ToolSpec] = []
        for t in self.tools:
            server, tool = t["server"], t["tool"]
            fq_name = f"mcp.{server}.{tool['name']}"
            args = tool.get("inputSchema") or tool.get("input_schema") or {}
            specs.append(
                ToolSpec(
                    name=fq_name,
                    description=tool.get("description", ""),
                    parameters=args,
                    run=self._make_runner(server, tool["name"]),
                )
            )
        return specs

    def _make_runner(self, server: str, tool: str):
        def run(ctx: Any, args: dict[str, Any]) -> str:
            client = self.clients.get(server)
            if client is None:
                return f"Unavailable: MCP server {server!r} is not running."
            try:
                result = client.call(tool, args)
            except McpUnavailable as exc:
                return f"Unavailable: {exc}"
            if result is None:
                return "ok"
            # _extract_content collapses the MCP envelope to a text string;
            # structured (non-content) results pass through for JSON rendering.
            if isinstance(result, dict) and "text" in result:
                return str(result["text"]).strip() or "ok"
            return json.dumps(result, default=str)

        return run

    def advertise(self) -> dict[str, Any]:
        return {
            "available": bool(self.tools),
            "tools": [f"{t['server']}.{t['tool']['name']}" for t in self.tools],
            "unavailable": self.unavailable,
        }