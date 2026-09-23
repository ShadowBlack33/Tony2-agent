"""API HTTP de la Etapa 1 (chat web). En Etapa 2 se agregan los webhooks de WhatsApp."""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.factory import build_agent

app = FastAPI(title="Tony2 Agent", version="0.1.0")
_agent = None
_sessions: dict[str, list[dict]] = {}  # E1: memoria en proceso. E2: Redis/PostgreSQL.
MAX_HISTORY = 20


def agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    session_id: str
    reply: str
    handoff: bool
    tools: list[str]


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    sid = body.session_id or uuid.uuid4().hex
    history = _sessions.get(sid, [])
    a = agent()
    a.tools.store.log_message(sid, "user", body.message)
    result, history = a.run_turn(sid, history, body.message)
    _sessions[sid] = history[-MAX_HISTORY:]
    a.tools.store.log_message(sid, "assistant", result.reply, ",".join(result.models),
                              result.cost_usd, result.latency_ms)
    return ChatOut(session_id=sid, reply=result.reply, handoff=result.handoff,
                   tools=[t["name"] for t in result.tool_calls])
