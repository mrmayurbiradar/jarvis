"""Workflow layer package (matrix row C6)."""
from __future__ import annotations

from app.config import Settings

from .base import WorkflowProvider, WorkflowUnavailable
from .local import LocalSchedulerWorkflowProvider
from .n8n import N8nWorkflowProvider


def build_workflow(settings: Settings) -> WorkflowProvider | None:
    """Construct the configured workflow provider.

    Engine selection (ADR-0004):
    - n8n (Hybrid/Remote) when ``n8n_base_url`` is set — wins over local.
    - Local in-process scheduler when ``workflows_dir`` is set (Local mode).
    - None otherwise — tools and the API then report the workflow layer as
      *unavailable* (graceful degradation, never a crash or a silent fake).

    The local scheduler is returned unstarted; ``create_app`` binds the agent
    tool executor and calls ``start()`` so scheduled jobs can actually run.
    """
    if settings.n8n_base_url:
        return N8nWorkflowProvider(
            base_url=settings.n8n_base_url,
            api_key=settings.n8n_api_key,
        )
    if settings.workflows_dir:
        provider = LocalSchedulerWorkflowProvider(settings.workflows_dir)
        return provider
    return None


__all__ = [
    "LocalSchedulerWorkflowProvider",
    "N8nWorkflowProvider",
    "WorkflowProvider",
    "WorkflowUnavailable",
    "build_workflow",
]