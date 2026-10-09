"""Mock/scripted LLM providers — for tests and keyless demos."""
from __future__ import annotations

from typing import Any

from .base import LlmProvider, LlmResult


class MockLlmProvider(LlmProvider):
    """Echoes the last user message with a prefix; never requests tools.

    Safe default for running the server without an API key.
    """

    def __init__(self, prefix: str = "(mock) ") -> None:
        self.prefix = prefix

    def complete(self, messages: list[dict[str, Any]], tools: list[Any]) -> LlmResult:
        last = messages[-1]["content"] if messages else ""
        return LlmResult(text=f"{self.prefix}{last}")


class ScriptedLlmProvider(LlmProvider):
    """Returns pre-scripted results in order — lets tests drive the agent loop."""

    def __init__(self, results: list[LlmResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def complete(self, messages: list[dict[str, Any]], tools: list[Any]) -> LlmResult:
        if self.calls >= len(self.results):
            raise RuntimeError("ScriptedLlmProvider exhausted")
        result = self.results[self.calls]
        self.calls += 1
        return result