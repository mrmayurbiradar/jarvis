"""Jira + email MCP server tests: not-configured degradation + parsing.

The live servers need real credentials, so the tests cover the two things
that are fully deterministic: graceful "not configured" behavior, and the
issue/subject parsing used to turn API/IMAP payloads into digest lines.
"""
from __future__ import annotations

import json
from email.message import Message
from unittest import mock

import pytest

from app.mcp.server import McpError
from app.mcp.servers.email import EmailMcpServer, _decode, _fmt_subject
from app.mcp.servers.jira import JiraMcpServer, _format_issue


# --- jira ---------------------------------------------------------------

def test_jira_returns_helpful_error_when_not_configured(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(McpError, match="not configured"):
        JiraMcpServer().call_tool("unresolved", {})


def test_jira_formats_issue():
    issue = {
        "key": "PROJ-123",
        "fields": {
            "summary": "  Fix the login bug   ",
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "description": "Users can't log in when the token expires.\nStep 2.",
        },
    }
    line = _format_issue(issue)
    assert "PROJ-123 [In Progress] (High)" in line
    assert "Fix the login bug" in line
    assert "token expires" in line


def test_jira_unresolved_parses_api_response(monkeypatch):
    import app.mcp.servers.jira as jira_mod

    monkeypatch.setenv("JIRA_BASE_URL", "https://acme.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "dev@acme.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    payload = {
        "issues": [
            {
                "key": "ACME-1",
                "fields": {"summary": "Ship v2", "status": {"name": "Open"}, "priority": {"name": "Medium"}},
            },
            {
                "key": "ACME-2",
                "fields": {"summary": "Fix CI", "status": {"name": "Open"}, "priority": {"name": "High"}},
            },
        ]
    }
    with mock.patch.object(jira_mod, "_get", return_value=payload):
        out = JiraMcpServer().call_tool("unresolved", {"max_results": 10})
    assert "ACME-1 [Open] (Medium) — Ship v2" in out
    assert "ACME-2 [Open] (High) — Fix CI" in out


def test_jira_unknown_tool_is_error():
    with pytest.raises(McpError, match="unknown tool"):
        JiraMcpServer().call_tool("nope", {})


# --- email ---------------------------------------------------------------

def test_email_returns_helpful_error_when_not_configured(monkeypatch):
    monkeypatch.delenv("EMAIL_IMAP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_IMAP_USER", raising=False)
    monkeypatch.delenv("EMAIL_IMAP_PASSWORD", raising=False)
    with pytest.raises(McpError, match="not configured"):
        EmailMcpServer().call_tool("unread", {})


def test_email_decodes_mime_words():
    assert _decode("=?UTF-8?B?SGVsbG8gV29ybGQ=?=") == "Hello World"
    assert _decode("Plain subject") == "Plain subject"


def test_email_subject_fallback():
    msg = Message()
    out = _fmt_subject(msg)
    assert out == "(no subject)"


def test_email_unknown_tool_is_error(monkeypatch):
    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("EMAIL_IMAP_USER", "a@example.com")
    monkeypatch.setenv("EMAIL_IMAP_PASSWORD", "pw")
    with pytest.raises(McpError, match="unknown tool"):
        EmailMcpServer().call_tool("nope", {})