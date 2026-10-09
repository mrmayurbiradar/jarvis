"""A tiny JSON-RPC 2.0-over-stdio MCP server base (stdlib only).

The MCP spec's stdio transport frames each message as
``Content-Length: <n>\\r\\n\\r\\n<json>``; this module provides the framing and
a minimal method set (``initialize``, ``notifications/initialized``,
``tools/list``, ``tools/call``) — exactly what JARVIS's tool bridge needs.
The server speaks the wire protocol; subclasses declare TF8 tools.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, BinaryIO

from app.mcp.protocol import INTERNAL_ERROR, METHOD_NOT_FOUND, encode_message, read_message

log = logging.getLogger(__name__)


class McpError(Exception):
    """Raised by a tool implementation; surfaced as a JSON-RPC error."""

    def __init__(self, message: str, code: int = -32000) -> None:
        super().__init__(message)
        self.code = code


class McpServer:
    """Base class for an MCP tool server executed as an independent process."""

    name = "jarvis-mcp-server"
    version = "0.1.0"

    # --- tools ---------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError

    # --- protocol loop --------------------------------------------------------

    def serve_forever(self, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
        stdin = stdin or sys.stdin.buffer
        stdout = stdout or sys.stdout.buffer
        log.info("mcp server '%s' listening", self.name)
        while True:
            try:
                msg = read_message(stdin)
            except EOFError:
                return
            if msg is None:
                continue  # transport closed cleanly → exit
            response = self._dispatch(msg)
            if response is not None:
                stdout.write(encode_message(response))
                stdout.flush()

    def _dispatch(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        request_id = msg.get("id")
        if request_id is None:
            # A JSON-RPC *notification* (no id) gets no reply.
            if msg.get("method") == "notifications/initialized":
                return None
            return None
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": self._initialize_result(params)}
        if method == "tools/list":
            try:
                return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.list_tools()}}
            except Exception as exc:  # noqa: BLE001
                return self._error(request_id, INTERNAL_ERROR, f"tools/list failed: {exc}")
        if method == "tools/call":
            try:
                name = params.get("name")
                arguments = params.get("arguments") or {}
                result = self.call_tool(name, arguments)
                if result is None:
                    content: list[dict[str, str]] = []
                else:
                    content = [
                        {"type": "text", "text": json.dumps(result, default=str)}
                        if not isinstance(result, str)
                        else {"type": "text", "text": result}
                    ]
                return {"jsonrpc": "2.0", "id": request_id, "result": {"content": content}}
            except McpError as exc:
                return self._error(request_id, exc.code, str(exc))
            except Exception as exc:
                log.exception("tools/call %s failed", params.get("name"))
                return self._error(request_id, INTERNAL_ERROR, str(exc))
        return self._error(request_id, METHOD_NOT_FOUND, f"unknown method {method!r}")

    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": params.get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self.name, "version": self.version},
        }

    @staticmethod
    def _error(request_id, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def start_jsonrpc_server(server: McpServer) -> None:
    """Entry point used by ``python -m app.mcp.servers.<name>``."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return