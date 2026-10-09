"""OpenAI-compatible chat-completions provider.

Uses only the standard library (urllib) so no extra dependency is required.
Any server implementing the `/v1/chat/completions` shape works (OpenAI,
local models via Ollama/LM Studio, etc.).
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from .base import LlmProvider, LlmResult, ToolCall


class OpenAICompatProvider(LlmProvider):
    def __init__(self, *, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def complete(self, messages: list[dict[str, Any]], tools: list[Any]) -> LlmResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": [_tool_schema(t) for t in tools],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        message = data["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"].get("arguments", "{}"),
            )
            for tc in message.get("tool_calls") or []
        ]
        return LlmResult(text=message.get("content"), tool_calls=tool_calls)


def _tool_schema(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }