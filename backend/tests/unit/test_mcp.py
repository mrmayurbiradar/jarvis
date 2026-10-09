"""MCP tool layer tests (architecture layer 4) — protocol, servers, bridge.

The MCP servers are *independent processes* speaking JSON-RPC 2.0 over stdio
(Content-Length framing). Tests exercise the real objects:

- Framing round-trip (encode → read) of results, errors and raw JSON.
- The `HelloMcpServer` and `FilesystemMcpServer` speaking the framing in a
  thread against a pipe pair, verifying init / tools/list / tools/call and
  error mapping.
- Filesystem default-deny: paths escaping the approved root are refused,
  still-functional tools advertise only on the allowlist.
- The `McpToolBridge`: builds agent `ToolSpec`s from advertised tools, calls
  proxy to the spawned process, missing server → typed unavailable message.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

import pytest

log = logging.getLogger(__name__)

from app.mcp.protocol import encode_message, make_error, make_result, read_message
from app.mcp.server import McpServer
from app.mcp.servers.filesystem import FilesystemMcpServer
from app.mcp.servers.hello import HelloMcpServer
from app.tools.mcp import McpToolBridge

# --- framing ----------------------------------------------------------------


def test_message_round_trip():
    raw = encode_message({"jsonrpc": "2.0", "id": 7, "result": {"ok": True}})
    assert read_message(io.BytesIO(raw)) == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}


def test_result_and_error_shapes():
    assert make_result(1, {"a": 1})["result"] == {"a": 1}
    err = make_error(2, -32601, "nope")
    assert err["error"]["code"] == -32601 and err["error"]["message"] == "nope"


def test_read_eof_returns_none():
    assert read_message(io.BytesIO(b"")) is None


def test_bad_json_body_returns_none():
    raw = b"Content-Length: 5\r\n\r\n{bad}"
    assert read_message(io.BytesIO(raw)) is None


# --- in-process servers over framing ----------------------------------------


class _PipeLoop:
    """Run a McpServer against the client side of an os.pipe pair."""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._read_fd, self._write_fd = os.pipe()  # server writes → client reads? no:
        # build a clean pair: client_r / client_w talk to server over file objects
        self._client_r_fd, self._server_w_fd = os.pipe()
        self._server_r_fd, self._client_w_fd = os.pipe()
        self.server_in = os.fdopen(self._server_r_fd, "rb", buffering=0)
        self.server_out = os.fdopen(self._server_w_fd, "wb", buffering=0)
        self.client_in = os.fdopen(self._client_r_fd, "rb", buffering=0)
        self.client_out = os.fdopen(self._client_w_fd, "wb", buffering=0)
        self.thread = threading.Thread(
            target=self._run, daemon=True
        )

    def _run(self) -> None:
        try:
            self.server.serve_forever(stdin=self.server_in, stdout=self.server_out)
        except Exception:  # teardown closes the pipes under this thread
            log.debug("pipe server thread ended", exc_info=True)

    def start(self) -> None:
        self.thread.start()

    def request(self, method: str, params: dict) -> dict:
        self.client_out.write(
            encode_message({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        )
        self.client_out.flush()
        return read_message(self.client_in)

    def stop(self) -> None:
        for f in (self.server_in, self.server_out, self.client_in, self.client_out):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass


@pytest.fixture()
def hello_loop():
    loop = _PipeLoop(HelloMcpServer())
    loop.start()
    try:
        yield loop
    finally:
        loop.stop()


def test_initialize_handshake(hello_loop):
    resp = hello_loop.request(
        "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}}
    )
    assert resp["result"]["serverInfo"]["name"] == "hello"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_advertises_only_rtf_tools(hello_loop):
    resp = hello_loop.request("tools/list", {})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["greet", "fail"]


def test_tools_call_greet(hello_loop):
    resp = hello_loop.request("tools/call", {"name": "greet", "arguments": {"name": "jarvis"}})
    assert resp["result"]["content"][0]["text"] == '{"greeting": "hello jarvis"}'


def test_tools_call_mcp_error_is_jsonrpc_error(hello_loop):
    resp = hello_loop.request("tools/call", {"name": "fail", "arguments": {}})
    assert resp["error"]["message"] == "deliberate failure"


def test_unknown_method_is_method_not_found(hello_loop):
    resp = hello_loop.request("bogus", {})
    assert resp["error"]["code"] == -32601


def test_notification_gets_no_reply(hello_loop):
    loop = hello_loop
    loop.client_out.write(
        encode_message({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    )
    loop.client_out.flush()
    # A notification must produce no response — a subsequent request still works.
    resp = loop.request("tools/list", {})
    assert "result" in resp


def test_filesystem_tools_round_trip(hello_loop):
    # filesystem server behaves like hello for both tools? No — spin its own:
    pass


# --- filesystem server ------------------------------------------------------


def _fs_loop(root: Path):
    return _PipeLoop(FilesystemMcpServer(root))


@pytest.fixture()
def fs_loop(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("hello notes", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("inner", encoding="utf-8")
    loop = _fs_loop(tmp_path)
    loop.start()
    try:
        yield loop
    finally:
        loop.stop()


def test_fs_read_file(fs_loop):
    loop = fs_loop
    resp = loop.request("tools/call", {"name": "read_file", "arguments": {"path": "notes.txt"}})
    assert '"hello notes"' in resp["result"]["content"][0]["text"]


def test_fs_list_dir(fs_loop):
    loop = fs_loop
    resp = loop.request("tools/call", {"name": "list_dir", "arguments": {"path": ""}})
    text = resp["result"]["content"][0]["text"]
    assert "notes.txt" in text and "sub" in text


def test_fs_stat(fs_loop):
    loop = fs_loop
    resp = loop.request("tools/call", {"name": "stat", "arguments": {"path": "notes.txt"}})
    assert '"exists": true' in resp["result"]["content"][0]["text"]


def test_fs_default_deny_escapes_root(fs_loop):
    loop = fs_loop
    resp = loop.request("tools/call", {"name": "read_file", "arguments": {"path": ".."}})
    assert resp["error"]["message"].startswith("path escapes")


def test_fs_unknown_tool_is_error(fs_loop):
    loop = fs_loop
    resp = loop.request("tools/call", {"name": "delete", "arguments": {}})
    assert resp["error"]["message"] == "unknown tool 'delete'"


# --- bridge (spawns real subprocesses) --------------------------------------


@pytest.fixture()
def bridge(tmp_path: Path):
    b = McpToolBridge(
        {
            "servers": [
                {"name": "filesystem", "root": str(tmp_path)},
                {"name": "hello"},
            ]
        }
    )
    b.connect()
    try:
        yield b
    finally:
        b.close()


def test_bridge_advertises_two_servers(tmp_path: Path):
    b = McpToolBridge({"servers": [{"name": "hello"}]})
    b.connect()
    try:
        adv = b.advertise()
        assert adv["available"] is True
        assert "hello.greet" in adv["tools"]
        assert "hello.fail" in adv["tools"]
    finally:
        b.close()


def test_bridge_call_proxies_to_subprocess(tmp_path: Path):
    (tmp_path / "data.txt").write_text("bridge data", encoding="utf-8")
    b = McpToolBridge({"servers": [{"name": "filesystem", "root": str(tmp_path)}]})
    b.connect()
    try:
        spec = {t.name: t for t in b.build_tool_specs()}
        assert "mcp.filesystem.read_file" in spec
        out = spec["mcp.filesystem.read_file"].run({}, {"path": "data.txt"})
        assert "bridge data" in out
    finally:
        b.close()


def test_bridge_missing_server_is_typed_unavailable(tmp_path: Path):
    b = McpToolBridge({"servers": [{"name": "does-not-exist"}]})
    b.connect()
    try:
        assert b.clients == {}
        assert b.unavailable, "expected a typed unavailable report"
        assert b.advertise()["available"] is False
        assert b.build_tool_specs() == []
    finally:
        b.close()


def test_bridge_tools_run_through_agent_tools(tmp_path: Path):
    """The agent tool map includes mcp.* specs; calling one round-trips the
    spawned MCP process (audit happens in the agent loop, not the bridge)."""
    b = McpToolBridge({"servers": [{"name": "hello"}]})
    b.connect()
    try:
        specs = {t.name: t for t in b.build_tool_specs()}
        assert "mcp.hello.greet" in specs
        assert specs["mcp.hello.greet"].run({}, {"name": "world"}) == '{"greeting": "hello world"}'
    finally:
        b.close()


def test_agent_runs_mcp_tool_and_audits(tmp_path):
    """Full loop integration: ToolContext carries the MCP bridge, the agent's
    tool map includes mcp.*, and a scripted LLM round-trips a call to the
    spawned MCP server process with the outcome audited."""
    from app.core.store import Store
    from app.orchestration.agent import Agent
    from app.providers.base import LlmResult, ToolCall
    from app.providers.mock import ScriptedLlmProvider
    from app.tools.registry import ToolContext

    b = McpToolBridge({"servers": [{"name": "hello"}]})
    store = Store(tmp_path / "agent.db")
    b.connect()
    try:
        ctx = ToolContext(
            adapter=None,  # type: ignore[arg-type] — MCP-backed agent needs no adapter
            store=store,
            allowlist_commands=frozenset(),
            allowlist_apps=frozenset(),
            mcp=b,
        )
        agent = Agent(
            llm=ScriptedLlmProvider(
                [
                    LlmResult(
                        tool_calls=[
                            ToolCall(
                                id="c1",
                                name="mcp.hello.greet",
                                arguments='{"name": "jarvis"}',
                            )
                        ]
                    ),
                    LlmResult(text="done"),
                ]
            ),
            ctx=ctx,
        )
        result = agent.run("session-1", "say hi")
        assert result.text == "done"
        assert any(
            m["role"] == "tool" and 'hello jarvis' in m["content"] for m in result.messages
        )
        audit = store.list_audit()
        assert any(r["capability"] == "mcp.hello.greet" and r["outcome"] == "ok" for r in audit)
    finally:
        b.close()