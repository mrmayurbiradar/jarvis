"""Agent chat endpoint (matrix row C2). Requires a paired worker token."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import require_worker_token
from app.core.deps import get_agent_dep
from app.orchestration.agent import Agent

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    text: str
    tool_calls: int


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    agent: Annotated[Agent, Depends(get_agent_dep)],
    _: Annotated[str, Depends(require_worker_token)],
) -> ChatResponse:
    session_id = body.session_id or uuid.uuid4().hex
    result = agent.run(session_id, body.message)
    return ChatResponse(
        session_id=result.session_id, text=result.text, tool_calls=result.tool_calls
    )