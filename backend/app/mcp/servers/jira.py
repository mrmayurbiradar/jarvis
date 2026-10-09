"""Jira MCP tool server — ticket triage for the morning routine.

Needs credentials via the environment (never committed):
    JIRA_BASE_URL   e.g. https://yourcompany.atlassian.net
    JIRA_EMAIL      your login email
    JIRA_API_TOKEN  an Atlassian API token (https://id.atlassian.com/manage-profile/security)

Tools (bridged to the agent as ``mcp.jira.<tool>``):
    unresolved(max_results)  issues assigned to you that are still open
    issue(key)               summary + status + priority + description of one issue

REST v3, stdlib-only (urllib). When the env is not set, calls return a
helpful "not configured" message — the agent degrades gracefully instead of
crashing (no-dangerous-substitution rule, ADR-0002).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from app.mcp.server import McpError, McpServer, start_jsonrpc_server

JQL_UNRESOLVED = 'assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC'


def _base_url() -> str:
    url = os.environ.get("JIRA_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise McpError("Jira not configured: set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN")
    return url


def _auth_header() -> dict[str, str]:
    email = os.environ.get("JIRA_EMAIL", "").strip()
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not (email and token):
        raise McpError("Jira not configured: set JIRA_EMAIL and JIRA_API_TOKEN")
    import base64

    cred = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {cred}", "Accept": "application/json"}


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _base_url() + path
    if params:
        import urllib.parse

        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_auth_header())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        raise McpError(f"Jira API {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise McpError(f"Jira unreachable: {exc.reason}") from exc


def _shorten(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _format_issue(issue: dict[str, Any]) -> str:
    key = issue.get("key", "")
    fields = issue.get("fields", {})
    summary = _shorten(fields.get("summary", ""))
    status = (fields.get("status") or {}).get("name", "?")
    priority = (fields.get("priority") or {}).get("name", "")
    desc = _shorten(fields.get("description") or "", 160)
    line = f"{key} [{status}]"
    if priority:
        line += f" ({priority})"
    line += f" — {summary}"
    if desc:
        line += f"\n    {desc}"
    return line


class JiraMcpServer(McpServer):
    name = "jira"
    version = "0.1.0"

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "unresolved",
                "description": "List Jira issues assigned to the user that are still open.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"max_results": {"type": "integer", "default": 10}},
                },
            },
            {
                "name": "issue",
                "description": "Get one Jira issue by key (summary, status, priority, description).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "unresolved":
            max_results = int(arguments.get("max_results", 10))
            data = _get("/rest/api/3/search", {"jql": JQL_UNRESOLVED, "maxResults": max_results, "fields": "summary,status,priority,description"})
            issues = data.get("issues", [])
            if not issues:
                return "No unresolved Jira issues assigned to you. "
            return "\n".join(_format_issue(i) for i in issues)
        if name == "issue":
            key = str(arguments.get("key", "")).strip()
            if not key:
                raise McpError("missing 'key'")
            data = _get(f"/rest/api/3/issue/{key}", {"fields": "summary,status,priority,description"})
            return _format_issue(data)
        raise McpError(f"unknown tool {name!r}")


if __name__ == "__main__":
    import sys

    sys.exit(start_jsonrpc_server(JiraMcpServer()))