"""Agent orchestration loop (matrix row C2).

Loop: user message → LLM → tool calls (each gated by policy + audit,
ADR-0005) → tool results → … until the LLM replies with text or the
iteration cap is hit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.policies import PolicyDenied
from app.execution.platform.base import UnsupportedCapability
from app.providers.base import LlmProvider
from app.tools.registry import ToolContext, build_tools


@dataclass
class AgentResult:
    session_id: str
    text: str
    tool_calls: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)


def _parse_args(arguments: str) -> dict[str, Any]:
    try:
        return json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return {}


class Agent:
    """Runs one conversational turn against the LLM and approved tools."""

    MAX_ITERATIONS = 5

    def __init__(
        self,
        llm: LlmProvider,
        ctx: ToolContext,
        *,
        require_approval: bool = False,
    ) -> None:
        self.llm = llm
        self.ctx = ctx
        self.require_approval = require_approval
        self.tools = {t.name: t for t in build_tools(ctx)}

    def run(self, session_id: str, user_text: str) -> AgentResult:
        messages = self.ctx.store.get_session_messages(session_id)
        messages.append({"role": "user", "content": user_text})
        tool_calls = 0
        for _ in range(self.MAX_ITERATIONS):
            result = self.llm.complete(messages, list(self.tools.values()))
            if not result.tool_calls:
                text = result.text or ""
                messages.append({"role": "assistant", "content": text})
                self.ctx.store.append_session_messages(session_id, messages)
                return AgentResult(
                    session_id=session_id, text=text, tool_calls=tool_calls, messages=messages
                )
            for tc in result.tool_calls:
                tool_calls += 1
                outcome = self._execute_tool(session_id, tc.name, _parse_args(tc.arguments))
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": outcome}
                )
        text = "I hit my iteration limit. Please try a more specific request."
        messages.append({"role": "assistant", "content": text})
        self.ctx.store.append_session_messages(session_id, messages)
        return AgentResult(
            session_id=session_id, text=text, tool_calls=tool_calls, messages=messages
        )

    def execute(
        self, actor: str, name: str, args: dict[str, Any], *, approved: bool = False
    ) -> str:
        """Run one tool through the full gate+audit path, outside a chat turn.

        Used by the in-process workflow scheduler (C6 local half): a scheduled
        step goes through exactly the same policy → approval → audit path as a
        chat-initiated call, so automation can never bypass the allowlists.

        ``approved=True`` skips gate 3 only — the caller already holds a human
        approval (POST /api/approvals/{id}/respond). Gates 1-2 still apply.
        """
        return self._execute_tool(actor, name, args, approved=approved)

    def _execute_tool(
        self,
        session_id: str,
        name: str,
        args: dict[str, Any],
        *,
        approved: bool = False,
    ) -> str:
        spec = self.tools.get(name)
        if spec is None:
            self._audit(session_id, name, args, "deny", "error", "unknown tool")
            return f"Error: unknown tool {name!r}"
        if spec.requires_approval and self.require_approval and not approved:
            # Gate 3 (ADR-0005): queue the action for a human, then report the
            # approval id so the client UI can resolve it.
            record = self.ctx.store.create_approval(session_id, name, args)
            self._audit(
                session_id,
                name,
                args,
                "deny",
                "blocked",
                f"awaiting human approval ({record['id']})",
            )
            return (
                f"Blocked: this action requires human approval"
                f" (approval {record['id']})"
            )
        if spec.policy is not None:
            try:
                spec.policy(args)
            except PolicyDenied as exc:
                self._audit(session_id, name, args, "deny", "rejected", str(exc))
                return f"Denied by policy: {exc}"
        if name.startswith("memory."):
            args.setdefault("session_id", session_id)
        try:
            out = spec.run(self.ctx, args) if spec.run else "ok"
        except UnsupportedCapability as exc:
            self._audit(session_id, name, args, "allow", "error", f"unsupported: {exc.reason}")
            return f"Unavailable on this platform: {exc.reason}"
        except Exception as exc:  # noqa: BLE001 — tool failures return to the model
            self._audit(session_id, name, args, "allow", "error", str(exc))
            return f"Tool failed: {exc}"
        self._audit(session_id, name, args, "allow", "ok", "")
        return out

    def _audit(
        self,
        session_id: str,
        capability: str,
        target: dict[str, Any],
        decision: str,
        outcome: str,
        reason: str,
    ) -> None:
        self.ctx.store.append_audit(
            actor=session_id,
            capability=capability,
            target=json.dumps(target, default=str),
            decision=decision,
            outcome=outcome,
            reason=reason,
        )