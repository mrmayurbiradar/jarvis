"""Filesystem MCP tool server (Layer 4).

Runs as an independent process::

    python -m app.mcp.servers.filesystem --root /Users/me/approved

Exposes read-only operations scoped to ``root`` (default-deny: paths outside
the allowlisted root are reported as errors, never silently served). The
backend spawns this process and bridges ``read_file``/``list_dir``/``stat``
into the agent's tool map as ``mcp.filesystem.*``.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from app.mcp.server import McpError, McpServer, start_jsonrpc_server

log = logging.getLogger(__name__)


class FilesystemMcpServer(McpServer):
    name = "filesystem"
    version = "0.1.0"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "read_file",
                "description": f"Read a text file under the approved root ({self.root}).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "path relative to root"}},
                    "required": ["path"],
                },
            },
            {
                "name": "list_dir",
                "description": f"List directory entries under the approved root ({self.root}).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "directory path or '' for root"}},
                    "required": ["path"],
                },
            },
            {
                "name": "stat",
                "description": f"Return metadata (exists, type, size) for a path under the approved root ({self.root}).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        path = arguments.get("path", "")
        try:
            resolved = self._resolve(path)
        except ValueError as exc:
            raise McpError(str(exc)) from exc
        if name == "read_file":
            if not resolved.is_file():
                raise McpError(f"not a readable file: {path!r}")
            return {"path": str(resolved), "content": resolved.read_text(encoding="utf-8")}
        if name == "list_dir":
            if not resolved.is_dir():
                raise McpError(f"not a directory: {path!r}")
            entries = sorted(
                (
                    {
                        "name": p.name,
                        "type": "dir" if p.is_dir() else "file",
                    }
                    for p in resolved.iterdir()
                ),
                key=lambda e: e["name"],
            )
            return {"path": str(resolved), "entries": entries}
        if name == "stat":
            return {
                "path": str(resolved),
                "exists": resolved.exists(),
                "is_dir": resolved.is_dir(),
                "is_file": resolved.is_file(),
                "size_bytes": resolved.stat().st_size if resolved.exists() else None,
            }
        raise ValueError(f"unknown tool {name!r}")

    def _resolve(self, rel: str) -> Path:
        candidate = (self.root / rel).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ValueError(f"path escapes the approved root: {rel!r}")
        return candidate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvis-mcp-filesystem")
    parser.add_argument("--root", required=True, help="approved root directory (default-deny)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    start_jsonrpc_server(FilesystemMcpServer(Path(args.root)))


if __name__ == "__main__":
    sys.exit(main())