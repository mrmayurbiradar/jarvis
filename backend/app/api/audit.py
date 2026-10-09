"""Audit log endpoint (matrix row C5). Requires a paired worker token."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import require_worker_token
from app.core.deps import get_store_dep
from app.core.store import Store

router = APIRouter(prefix="/api", tags=["audit"])


class AuditEntry(BaseModel):
    ts: str
    actor: str
    capability: str
    target: str = ""
    decision: str
    outcome: str
    reason: str = ""


@router.get("/audit", response_model=list[AuditEntry])
def audit_log(
    limit: int = 50,
    store: Annotated[Store, Depends(get_store_dep)] = ...,
    _: Annotated[str, Depends(require_worker_token)] = ...,
) -> list[AuditEntry]:
    return [AuditEntry(**row) for row in store.list_audit(limit)]