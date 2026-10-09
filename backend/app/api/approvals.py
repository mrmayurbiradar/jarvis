"""Gate-3 approval surface (ADR-0005): pending actions + human response.

Chat and scheduled steps that hit a ``requires_approval`` tool queue a
pending record here instead of silently running. The client UI polls
``GET /api/approvals/pending`` and posts a decision; an approval re-executes
the action through the same policy → audit path (gates 1-2 still apply), a
denial records a reject audit entry. This router is backend-only — the UI
wiring lives in the clients.
"""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_worker_token
from app.core.deps import get_agent_dep, get_store_dep
from app.core.store import Store
from app.orchestration.agent import Agent

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalEntry(BaseModel):
    id: str
    session_id: str
    capability: str
    target: dict
    status: str
    created_at: str


class RespondRequest(BaseModel):
    decision: str  # "approve" | "deny"
    responder: str = "worker"


class RespondResponse(BaseModel):
    id: str
    status: str
    result: str = ""


def _entry(row: dict) -> ApprovalEntry:
    try:
        target = json.loads(row["target"] or "{}")
    except ValueError:
        target = {}
    return ApprovalEntry(**{**row, "target": target})


@router.get("/pending", response_model=list[ApprovalEntry])
def pending_approvals(
    store: Annotated[Store, Depends(get_store_dep)] = ...,
    _: Annotated[str, Depends(require_worker_token)] = ...,
) -> list[ApprovalEntry]:
    return [_entry(row) for row in store.list_pending_approvals()]


@router.post("/{approval_id}/respond", response_model=RespondResponse)
def respond(
    approval_id: str,
    body: RespondRequest,
    store: Annotated[Store, Depends(get_store_dep)] = ...,
    agent: Annotated[Agent, Depends(get_agent_dep)] = ...,
    _: Annotated[str, Depends(require_worker_token)] = ...,
) -> RespondResponse:
    if body.decision not in ("approve", "deny"):
        raise HTTPException(status_code=422, detail="decision must be 'approve' or 'deny'")
    record = store.get_approval(approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="approval not found")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {record['status']}")
    try:
        target = json.loads(record["target"] or "{}")
    except ValueError:
        target = {}
    if body.decision == "approve":
        # Human approval satisfies gate 3; the tool still runs gates 1-2 and
        # is audited exactly like a chat-initiated call.
        result = agent.execute(
            record["session_id"], record["capability"], target, approved=True
        )
        store.respond_approval(approval_id, "approved", body.responder)
        return RespondResponse(id=approval_id, status="approved", result=result)
    store.append_audit(
        actor=record["session_id"],
        capability=record["capability"],
        target=record["target"],
        decision="deny",
        outcome="rejected",
        reason=f"human denied approval ({approval_id})",
    )
    store.respond_approval(approval_id, "denied", body.responder)
    return RespondResponse(id=approval_id, status="denied")