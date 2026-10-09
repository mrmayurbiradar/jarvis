"""Workflow-layer API (matrix row C6): engine health + workflow listing.

Both endpoints require a worker token (ADR-0005 gate 1). If no workflow
provider is configured they return 501 with a capability/reason payload,
mirroring the `UnsupportedCapability` contract — a missing integration is
reported, never silently skipped or faked.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_worker_token
from app.core.deps import get_workflow_dep
from app.workflows.base import WorkflowProvider, WorkflowUnavailable

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


def _unconfigured() -> HTTPException:
    return HTTPException(
        status_code=501,
        detail={"capability": "workflow", "reason": "no workflow provider configured"},
    )


def _unreachable(exc: WorkflowUnavailable) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"capability": "workflow", "reason": exc.reason},
    )


@router.get("/health")
def workflow_health(
    _: Annotated[str, Depends(require_worker_token)],
    workflow: Annotated[WorkflowProvider | None, Depends(get_workflow_dep)],
) -> dict[str, Any]:
    if workflow is None:
        raise _unconfigured()
    try:
        return workflow.health()
    except WorkflowUnavailable as exc:
        raise _unreachable(exc) from exc


@router.get("/list")
def workflow_list(
    _: Annotated[str, Depends(require_worker_token)],
    workflow: Annotated[WorkflowProvider | None, Depends(get_workflow_dep)],
) -> dict[str, Any]:
    if workflow is None:
        raise _unconfigured()
    try:
        return {"workflows": workflow.list_workflows()}
    except WorkflowUnavailable as exc:
        raise _unreachable(exc) from exc