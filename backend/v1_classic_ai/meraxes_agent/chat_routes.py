"""Agent chat API — sessions, history, multi-source research replies."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

V1_ROOT = Path(__file__).resolve().parents[1]
if str(V1_ROOT) not in sys.path:
    sys.path.insert(0, str(V1_ROOT))

from meraxes_agent import chat_service

router = APIRouter(prefix="/agents/chat", tags=["agent-chat"])


class NewSessionRequest(BaseModel):
    bot_id: str | None = None
    dataset: str = Field(default="saas")
    client_id: str | None = None


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    enable_research: bool = True
    bot_id: str | None = None
    dataset: str | None = None


@router.get("/capabilities")
def capabilities():
    return chat_service.chat_capabilities()


@router.get("/sessions")
def list_sessions(client_id: str | None = None, limit: int = 40):
    return {"sessions": chat_service.sessions_list(client_id=client_id, limit=limit)}


@router.post("/sessions")
def create_session(body: NewSessionRequest):
    return chat_service.new_session(
        bot_id=body.bot_id,
        dataset=body.dataset,
        client_id=body.client_id,
    )


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    from database import get_chat_session

    s = get_chat_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {
        **s,
        "messages": chat_service.session_history(session_id),
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, client_id: str | None = None):
    n = chat_service.remove_session(session_id, client_id=client_id)
    if not n:
        raise HTTPException(404, "Session not found")
    return {"deleted": True, "session_id": session_id}


@router.get("/jobs/{job_id}")
def get_action_job(job_id: str):
    job = chat_service.get_action_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: ChatMessageRequest):
    try:
        return await chat_service.agent_chat_turn(
            session_id,
            body.message,
            enable_research=body.enable_research,
            bot_id=body.bot_id,
            dataset=body.dataset,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
