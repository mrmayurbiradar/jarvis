"""Provider layer package."""
from __future__ import annotations

from app.config import Settings

from .base import LlmProvider
from .mock import MockLlmProvider
from .openai_compat import OpenAICompatProvider


def build_llm(settings: Settings) -> LlmProvider:
    """Construct the configured LLM provider (matrix row C7)."""
    if settings.llm_provider == "openai":
        return OpenAICompatProvider(
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )
    return MockLlmProvider()