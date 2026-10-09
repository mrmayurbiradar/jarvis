"""Worker-token auth (ADR-0005 gate 1: explicit pairing).

A worker (or client) proves identity by presenting a bearer token that was
issued by confirming a pairing code. Tokens are stored hashed; verification
is constant-time. Revocation invalidates a token immediately.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.deps import get_store_dep
from app.core.store import Store


def require_worker_token(
    authorization: Annotated[str | None, Header()] = None,
    store: Annotated[Store, Depends(get_store_dep)] = ...,
) -> str:
    """Return the verified worker token, or raise 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token or not store.verify_worker_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or revoked worker token",
        )
    return token