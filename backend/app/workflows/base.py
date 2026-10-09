"""Workflow layer — replaceable workflow providers (matrix row C6).

Hybrid/Remote mode bridges to a self-hosted n8n instance (``n8n.py``);
Local-only mode substitutes an in-process scheduler (future slice). The rest
of the backend depends only on the ``WorkflowProvider`` interface, so the
engine is swapped by configuration without touching core logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WorkflowUnavailable(Exception):
    """The workflow engine is unreachable or misconfigured.

    Raised instead of crashing so tools and the API can degrade gracefully —
    the no-dangerous-substitution rule from ADR-0002: a missing integration
    surfaces as *unsupported*, it is never silently skipped or faked.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class WorkflowProvider(ABC):
    """Workflow engine client (n8n or a local scheduler)."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return engine health; raises WorkflowUnavailable when unreachable."""

    @abstractmethod
    def list_workflows(self) -> list[dict[str, Any]]:
        """Enumerate the workflows/automations available on the engine."""

    @abstractmethod
    def run_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger a workflow with the given input payload."""