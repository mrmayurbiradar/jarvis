"""MCP wire protocol — the subset JARVIS speaks over stdio (JSON-RPC 2.0).

Model Context Protocol transports messages as JSON-RPC 2.0 frames. On stdio
the framing is:

    Content-Length: <bytes>\r\n
    \r\n
    <json body>

Only the three methods the JARVIS backends needs are implemented — anything
else is out of scope for the tool bridge and returned as a method-not-found
error:

- ``initialize``            → capability/version handshake
- ``notifications/initialized`` → ack (ignored; a JSON-RPC *notification* has no ``id``)
- ``tools/list``            → {tools: [{name, description, inputSchema}]}
- ``tools/call``            → {content: [{type: "text", text}], isError}

The whole protocol is stdlib-only (``json``), matching the n8n bridge and the
OpenAI-compatible LLM provider — no SDK dependency.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, BinaryIO

PROTOCOL_VERSION = "2025-03-26"

# JSON-RPC 2.0 error codes we care about.
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

_MAX_BODY_BYTES = 8 * 1024 * 1024


def encode_message(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one Content-Length-framed JSON-RPC message; None on clean EOF."""
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:  # EOF
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii").partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", 0))
    if length <= 0 or length > _MAX_BODY_BYTES:
        return None
    body = stream.read(length)
    if len(body) != length:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def make_request(method: str, params: Any, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def make_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@dataclass(frozen=True)
class McpTool:
    """A tool advertised by an MCP server (subset of the spec's Tool object)."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema or {"type": "object", "properties": {}},
        }


@dataclass(frozen=True)
class McpToolResult:
    """Result of ``tools/call``."""

    content: Any
    is_error: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": str(self.content)}] if self.content is not None else [],
            "isError": self.is_error,
        }