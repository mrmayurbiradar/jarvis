"""Email MCP tool server — unread-message digest for the morning routine.

Needs credentials via the environment (never committed):
    EMAIL_IMAP_HOST       e.g. imap.gmail.com / outlook.office365.com
    EMAIL_IMAP_USER       your full email address
    EMAIL_IMAP_PASSWORD   an app password (Gmail: Google account → App passwords)
    EMAIL_IMAP_PORT       optional, default 993
    EMAIL_IMAP_FOLDER     optional, default INBOX

Tools (bridged to the agent as ``mcp.email.<tool>``):
    unread(limit)   subjects/senders of the newest unread messages
    folders()       available mailbox folders (for debugging)

Stdlib-only (imaplib + email). Unconfigured → helpful message, never a crash.
"""
from __future__ import annotations

import email
import imaplib
import os
from email.header import decode_header
from typing import Any

from app.mcp.server import McpError, McpServer, start_jsonrpc_server


def _config() -> tuple[str, str, str, int, str]:
    host = os.environ.get("EMAIL_IMAP_HOST", "").strip()
    user = os.environ.get("EMAIL_IMAP_USER", "").strip()
    password = os.environ.get("EMAIL_IMAP_PASSWORD", "").strip()
    if not (host and user and password):
        raise McpError(
            "Email not configured: set EMAIL_IMAP_HOST, EMAIL_IMAP_USER and EMAIL_IMAP_PASSWORD"
        )
    port = int(os.environ.get("EMAIL_IMAP_PORT", "993"))
    folder = os.environ.get("EMAIL_IMAP_FOLDER", "INBOX").strip()
    return host, user, password, port, folder


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(charset or "utf-8", "replace"))
            except LookupError:
                out.append(text.decode("utf-8", "replace"))
        else:
            out.append(text)
    return " ".join("".join(out).split())


def _fmt_subject(message: email.message.Message) -> str:
    subject = _decode(message.get("Subject"))
    return subject[:120] or "(no subject)"


class EmailMcpServer(McpServer):
    name = "email"
    version = "0.1.0"

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "unread",
                "description": "List the newest unread email messages (sender + subject).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                },
            },
            {
                "name": "folders",
                "description": "List available IMAP mailbox folders.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def _connect(self) -> imaplib.IMAP4_SSL:
        host, user, password, port, _ = _config()
        try:
            conn = imaplib.IMAP4_SSL(host, port)
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"cannot connect to {host}: {exc}") from exc
        try:
            conn.login(user, password)
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"login failed for {user}: {exc}") from exc
        return conn

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in ("unread", "folders"):
            raise McpError(f"unknown tool {name!r}")
        conn = self._connect()
        try:
            if name == "folders":
                status, data = conn.list()
                if status != "OK":
                    raise McpError("listing folders failed")
                return "\n".join(d.decode("utf-8", "replace") for d in data if isinstance(d, bytes))
            limit = int(arguments.get("limit", 10))
            _, _, folder = _config()
            status, _ = conn.select(folder, readonly=True)
            if status != "OK":
                raise McpError(f"cannot select folder {folder!r}")
            status, data = conn.search(None, "UNSEEN")
            if status != "OK":
                raise McpError("search UNSEEN failed")
            ids = (data[0] or b"").split()
            if not ids:
                return "No unread email."
            rows = []
            for msg_id in ids[-limit:]:
                _, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                message = email.message_from_bytes(msg_data[0][1])
                sender = _decode(message.get("From")).replace("<", "(").replace(">", ")")
                rows.append(f"{_fmt_subject(message)} — {sender}")
            return "\n".join(rows) if rows else "No unread email."
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    import sys

    sys.exit(start_jsonrpc_server(EmailMcpServer()))