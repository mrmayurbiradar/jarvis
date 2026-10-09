"""Pairing endpoints (ADR-0005 gate 1): request + confirm a device code.

The returned bearer token authorizes worker/agent endpoints. Confirm moves
behind human auth when the client UI exists; today the code is the
one-time secret.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_store_dep
from app.core.store import Store

router = APIRouter(prefix="/api/pair", tags=["pairing"])


class PairRequest(BaseModel):
    display_name: str


class PairResponse(BaseModel):
    pairing_id: str
    code: str
    expires_at: str
    verification_uri: str


class ConfirmRequest(BaseModel):
    code: str


class ConfirmResponse(BaseModel):
    token: str
    expires_in: int


@router.post("/request", response_model=PairResponse)
def request_pairing(
    body: PairRequest, store: Annotated[Store, Depends(get_store_dep)]
) -> PairResponse:
    r = store.request_pairing(body.display_name)
    return PairResponse(
        pairing_id=r["pairing_id"],
        code=r["code"],
        expires_at=r["expires_at"],
        verification_uri=f"/pair/confirm?code={r['code']}",
    )


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_pairing(
    body: ConfirmRequest, store: Annotated[Store, Depends(get_store_dep)]
) -> ConfirmResponse:
    token = store.confirm_pairing(body.code)
    if token is None:
        raise HTTPException(status_code=404, detail="invalid or expired pairing code")
    return ConfirmResponse(token=token, expires_in=store.ttl_seconds)