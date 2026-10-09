"""Echo/hello MCP tool server — integration-test fixture for the bridge."""
from __future__ import annotations

import sys
from typing import Any

from app.mcp.server import McpError, McpServer, start_jsonrpc_server


class HelloMcpServer(McpServer):
    name = "hello"
    version = "0.1.0"

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "greet",
                "description": "Greet someone by name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            {
                "name": "fail",
                "description": "Always raises — tests error/result mapping.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "greet":
            return {"greeting": f"hello {arguments.get('name', 'world')}"}
        if name == "fail":
            raise McpError("deliberate failure")
        raise McpError(f"unknown tool {name!r}")


if __name__ == "__main__":
    sys.exit(start_jsonrpc_server(HelloMcpServer()))