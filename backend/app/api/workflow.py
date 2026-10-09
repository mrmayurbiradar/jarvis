"""Workflow-layer API (matrix row C6): engine health + workflow listing.

Both endpoints require a worker token (ADR-0005 gate 1). If no workflow
provider is configured they return 501 with a capability/reason payload,
mirroring the `UnsupportedCapability` contract — a missing integration is
reported, never silently skipped or faked.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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


class RunWorkflowRequest(BaseModel):
    payload: dict[str, Any] = {}


@router.post("/{workflow_id}/run")
def workflow_run(
    workflow_id: str,
    _: Annotated[str, Depends(require_worker_token)],
    workflow: Annotated[WorkflowProvider | None, Depends(get_workflow_dep)],
    body: RunWorkflowRequest | None = None,
) -> dict[str, Any]:
    """Run a workflow's steps immediately (the n8n webhook analogy).

    Steps execute through the agent's tool executor — the same policy →
    approval → audit path as a chat request — so firing an automation can
    never bypass the allowlists. ``{{input.<key>}}`` templates in step args
    interpolate values from the payload.
    """
    if workflow is None:
        raise _unconfigured()
    try:
        return workflow.run_workflow(workflow_id, (body or RunWorkflowRequest()).payload)
    except WorkflowUnavailable as exc:
        status = 404 if "no workflow named" in str(exc) else 502
        raise HTTPException(
            status_code=status, detail={"capability": "workflow", "reason": exc.reason}
        ) from exc