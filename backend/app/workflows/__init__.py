"""Workflow layer package (matrix row C6)."""
from __future__ import annotations

from app.config import Settings

from .base import WorkflowProvider, WorkflowUnavailable
from .n8n import N8nWorkflowProvider


def build_workflow(settings: Settings) -> WorkflowProvider | None:
    """Construct the configured workflow provider.

    Returns None when no engine is configured — tools and the API then report
    the workflow layer as *unavailable* (graceful degradation, never a crash
    or a silent fake). Local-only mode substitutes an in-process scheduler
    (future slice); for now, local mode simply has no workflow engine.
    """
    if settings.n8n_base_url:
        return N8nWorkflowProvider(
            base_url=settings.n8n_base_url,
            api_key=settings.n8n_api_key,
        )
    return None


__all__ = ["N8nWorkflowProvider", "WorkflowProvider", "WorkflowUnavailable", "build_workflow"]