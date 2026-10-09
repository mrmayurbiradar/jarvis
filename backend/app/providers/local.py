"""Keyless local agent brain (matrix row C7, local mode).

Routes natural-language daily-work requests to the tool set and composes a
reply that can be spoken back — no API key, no network to a model host. The
same tools get full LLM reasoning when JARVIS_LLM_PROVIDER=openai is set;
this provider is the always-available fallback that makes talking to the
agent actually do things.

Design notes:
* Stateless across turns: every reply is derived from the message history
  alone (the agent appends tool results and calls complete() again), so
  interleaved sessions can't corrupt each other.
* If a request doesn't match an intent it falls back to a short help text
  that teaches the user what the agent can do.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from .base import LlmProvider, LlmResult, ToolCall

_RE = re.IGNORECASE

# Ordered intent rules: (compiled regex, handler name). First match wins —
# the order matters, put the most specific rules first.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(good morning|start my day|morning briefing|daily briefing|daily digest|brief me|today'?s briefing|what'?s (new|up) (today|this morning)|what (is|are) (on|in) (my|today'?s) (agenda|plan))\b", _RE), "briefing"),
    (re.compile(r"^(hey\s+)?(jarvis\s+)?(hello|hi|hey|yo|sup|good\s+(morning|afternoon|evening))\b", _RE), "greet"),
    (re.compile(r"what('s| is| are)? (on )?(my )?(tasks?|todos?|to-?dos?|to-?do\s+list)\b|show (me )?(my )?(tasks?|todos?|list)\b", _RE), "tasks.list"),
    (re.compile(r"\btask\s*([A-Za-z0-9]{4,})\s+(is\s+)?done\b", _RE), "tasks.done"),
    (re.compile(r"\b(mark|finish|complete|check\s*off)\s+(.+?)(\s+as\s+done)?\s*$", _RE), "tasks.done"),
    (re.compile(r"\bdone\s+with\s+(.+)$", _RE), "tasks.done"),
    (re.compile(r"\b(add|make|create|new)\b.*\b(task|todo|to-?do|item)\b|add\s+.+to\s+(my\s+)?(tasks|todo|list)\b|\bremind\s+me\s+to\b|\bdon't\s+forget\s+to\b", _RE), "tasks.add"),
    (re.compile(r"\b(take|make|write|jot|note)\s+(a\s+)?note\b|\bnote\s+down\b|\bnote\s*[:,-]", _RE), "notes.append"),
    (re.compile(r"what did i note|show\s+(my|me)\s+(today'?s\s+)?notes|read\s+(my\s+)?notes|today'?s\s+notes", _RE), "notes.today"),
    (re.compile(r"\bweather\b|\bforecast\b|\btemperature\b|how\s+(hot|cold)\s+is\s+it\b|is\s+it\s+(raining|sunny|cold|hot)\b", _RE), "weather"),
    (re.compile(r"what('s| is)? the time\b|current time\b|what time is it\b|the date\b|today'?s date\b|what day", _RE), "now"),
    (re.compile(r"remember\s+that\b|remember\s*[:,-]|note\s+that\b|keep\s+in\s+mind", _RE), "memory.store"),
    (re.compile(r"what do you (remember|know)\b|search\s+(your\s+)?(memory|notes)|recall\b", _RE), "memory.recall"),
    (re.compile(r"list\s+(my\s+)?files\b|what files\b|files\s+in\b|show\s+(my\s+)?files\b", _RE), "files.list"),
    (re.compile(r"\bread\s+(the\s+)?(file\s+)?([\w./-]+)\s*$|open\s+(the\s+)?file\s+([\w./-]+)\s*$|show\s+(the\s+)?contents\s+of\s+([\w./-]+)", _RE), "files.read"),
]

# Prefixes to strip when extracting the payload after an intent keyword.
_ADD_PREFIXES = (
    "add a task", "add task", "add a todo", "add todo", "add an item",
    "add to my todo", "add to my task list", "add to my tasks",
    "new task", "new todo", "remind me to", "don't forget to", "remember to", "add",
)
_NOTE_PREFIXES = (
    "take a note", "make a note", "write a note", "jot down a note",
    "note down", "take note", "make note", "jot down", "write down", "note",
)
_DONE_PREFIXES = ("mark", "finish", "complete", "check off", "check")
_STRIP_END = re.compile(r"\s*(?:(?:as\s+)?done)?\s*[:.,-]?\s*$")


def _after(text: str, prefixes: tuple[str, ...]) -> str | None:
    """Return text after the first matching prefix, stripped; None if empty."""
    lowered = text.lower()
    best = None
    for prefix in prefixes:
        idx = lowered.find(prefix)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, len(prefix))
    if best is None:
        return None
    rest = text[best[0] + best[1]:]
    rest = _STRIP_END.sub("", rest).strip(" \t\"'“”")
    # drop leading separators and "to" (remind me to X)
    rest = re.sub(r"^\s*[:.,\-—\s]+\s*", "", rest)
    rest = re.sub(r"^to\s+", "", rest).strip()
    return rest or None


def _extract_done(text: str) -> str | None:
    """Pull the target of a done/mark/finish phrase."""
    m = re.search(r"\btask\s*([A-Za-z0-9]{4,})\s+(is\s+)?done\b", text, _RE)
    if m:
        return m.group(1)
    m = re.search(r"\bdone\s+with\s+(.+)$", text, _RE)
    if m:
        return m.group(1).strip().strip(".")
    for prefix in _DONE_PREFIXES:
        idx = text.lower().find(prefix)
        if idx >= 0:
            rest = text[idx + len(prefix):].strip(" \t:,-")
            rest = _STRIP_END.sub("", rest).strip()
            return rest or None
    return None


def _extract_file(text: str) -> str | None:
    m = re.search(r"(?:read|open\s+(?:the\s+)?file|show\s+(?:the\s+)?contents\s+of)\s+(?:the\s+)?(?:file\s+)?([\w./-]+)", text, _RE)
    return m.group(1) if m else None


def _now_text() -> str:
    now = datetime.now().astimezone()
    return now.strftime("It's %A, %B %-d — %-I:%M %p.")


def _greeting() -> str:
    now = datetime.now().astimezone()
    return (
        f"Hello. It's {now.strftime('%A, %B %-d')}. "
        "Say 'start my day' for your morning briefing — gold rate, news, weather, "
        "tasks, notes and approvals. Or just ask for tasks, notes, weather or files."
    )


_HELP = (
    "I can help with daily work — try: "
    "\"add a task: buy groceries\", "
    "\"what's my todo?\", "
    "\"mark buy groceries done\", "
    "\"take a note: call Sam at 4\", "
    "\"what did I note today?\", "
    "\"how's the weather?\", "
    "\"what time is it?\", "
    "\"remember that my desk is on the 4th floor\", "
    "\"what do you remember about desk\", "
    "\"list my files\", or "
    "\"read README.md\". "
    "Add an OpenAI key (JARVIS_LLM_PROVIDER=openai) for open-ended conversation."
)


class LocalAgentProvider(LlmProvider):
    """Intent-routing provider: understands daily-work requests, calls tools,
    and composes a spoken-friendly reply — no API key required."""

    def complete(self, messages: list[dict[str, Any]], tools: list[Any]) -> LlmResult:
        # Tool results arrive as role="tool" messages after a routed tool call.
        if messages and messages[-1].get("role") == "tool":
            return LlmResult(text=self._reply_from_tools(messages))
        text = (messages[-1].get("content") or "").strip() if messages else ""
        return self._route(text)

    # -- routing -----------------------------------------------------------

    def _route(self, text: str) -> LlmResult:
        lowered = text.lower().strip()
        if not lowered:
            return LlmResult(text=_HELP)
        for pattern, intent in _RULES:
            if not pattern.search(lowered):
                continue
            if intent == "greet":
                return LlmResult(text=_greeting())
            if intent == "briefing":
                return LlmResult(tool_calls=[self._call("briefing.now", {})])
            if intent == "now":
                return LlmResult(text=_now_text())
            if intent == "tasks.list":
                return LlmResult(tool_calls=[self._call("tasks.list", {})])
            if intent == "tasks.add":
                payload = _after(text, _ADD_PREFIXES)
                if payload is None:
                    return LlmResult(text="What should I add to your tasks?")
                return LlmResult(tool_calls=[self._call("tasks.add", {"text": payload})])
            if intent == "tasks.done":
                target = _extract_done(text)
                if target is None:
                    return LlmResult(text="Which task should I mark done?")
                if re.fullmatch(r"[A-Za-z0-9]{4,}", target or ""):
                    return LlmResult(tool_calls=[self._call("tasks.done", {"id": target})])
                return LlmResult(tool_calls=[self._call("tasks.done", {"text": target})])
            if intent == "notes.append":
                payload = _after(text, _NOTE_PREFIXES)
                if payload is None:
                    return LlmResult(text="What should I write down?")
                return LlmResult(tool_calls=[self._call("notes.append", {"text": payload})])
            if intent == "notes.today":
                return LlmResult(tool_calls=[self._call("notes.today", {})])
            if intent == "weather":
                m = re.search(r"\bweather\s+(in|for|at)\s+(.+)$|forecast\s+(?:for\s+)?(.+)$", text, _RE)
                loc = (m.group(2) or m.group(3) or "").strip(" ?.!,;:") if m else ""
                return LlmResult(tool_calls=[self._call("weather.now", {"location": loc} if loc else {})])
            if intent == "memory.store":
                payload = _after(text, ("remember that", "remember:", "note that", "keep in mind"))
                if payload is None:
                    return LlmResult(text="What should I remember?")
                return LlmResult(tool_calls=[self._call("memory.store", {"fact": payload})])
            if intent == "memory.recall":
                m = re.search(r"(?:remember|know|recall|search)\s+(?:about\s+)?(.+)$", text, _RE)
                q = m.group(1).strip(" ?.!,:") if m else ""
                return LlmResult(tool_calls=[self._call("memory.recall", {"query": q})])
            if intent == "files.list":
                return LlmResult(tool_calls=[self._call("files.list", {})])
            if intent == "files.read":
                path = _extract_file(text)
                if path is None:
                    return LlmResult(text="Which file should I read?")
                return LlmResult(tool_calls=[self._call("files.read", {"path": path})])
        return LlmResult(text=_HELP)

    @staticmethod
    def _call(name: str, arguments: dict[str, Any]) -> ToolCall:
        return ToolCall(id=uuid.uuid4().hex, name=name, arguments=json.dumps(arguments))

    # -- reply composition --------------------------------------------------

    @staticmethod
    def _reply_from_tools(messages: list[dict[str, Any]]) -> str:
        tool = messages[-1]
        name = tool.get("name", "")
        content = (tool.get("content") or "").strip()
        if name == "tasks.add":
            text = content.removeprefix("added ").split(" (")[0].strip('"')
            return f'Done — added "{text}" to your to-do list.'
        if name == "tasks.list":
            if content.startswith("No open tasks"):
                return "Your to-do list is clear — nothing pending."
            return "Here's your to-do list:\n" + content
        if name == "tasks.done":
            if content.startswith("not found"):
                return "I couldn't find an open task matching that."
            return "Done — marked it complete."
        if name == "notes.append":
            return "Saved to your daily journal."
        if name == "notes.today":
            return content if not content.startswith("No notes") else "Nothing noted yet today."
        if name == "weather.now":
            return "Weather right now: " + content
        if name == "files.list":
            return "Workspace:\n" + content
        if name == "files.read":
            return content
        if name == "briefing.now":
            return content
        if name == "memory.store":
            return "Remembered."
        if name == "memory.recall":
            try:
                rows = json.loads(content)
            except (ValueError, TypeError):
                return content
            if not rows:
                return "I don't remember anything matching that yet."
            facts = [r.get("fact", "") for r in rows[:5]]
            return "Here's what I remember:\n" + "\n".join(f"- {f}" for f in facts)
        return content or "Done."