"""Provider layer — replaceable AI models, speech, TTS, data (matrix row C7).

The rest of the backend depends only on these interfaces, so providers can
be swapped by configuration without touching core logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON-encoded arguments


@dataclass
class LlmResult:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LlmProvider(ABC):
    """Chat-completion provider with tool-call support."""

    @abstractmethod
    def complete(self, messages: list[dict[str, Any]], tools: list[Any]) -> LlmResult:
        """Complete a conversation; may request tool calls."""