"""Provider layer package."""
from __future__ import annotations

from app.config import Settings

from .base import LlmProvider
from .local import LocalAgentProvider
from .mock import MockLlmProvider
from .openai_compat import OpenAICompatProvider


def build_llm(settings: Settings) -> LlmProvider:
    """Construct the configured LLM provider (matrix row C7).

    "local" (default) is the keyless intent-routing brain that makes the
    agent useful without any API key; "openai" upgrades it to full
    conversational reasoning; "mock" is a test echo.
    """
    if settings.llm_provider == "openai":
        return OpenAICompatProvider(
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )
    if settings.llm_provider == "local":
        return LocalAgentProvider()
    return MockLlmProvider()