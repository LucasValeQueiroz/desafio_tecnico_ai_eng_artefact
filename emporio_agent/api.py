"""Thin HTTP interface over the agent. All responses use the { data, meta, error } envelope."""
from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .agent import MAX_MESSAGE_CHARS, ServiceAgent
from .config import load_settings

CHAT_PAGE = Path(__file__).parent / "static" / "index.html"


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


def _envelope(data=None, meta: dict | None = None, error: dict | None = None, status: int = 200) -> JSONResponse:
    meta = {"request_id": str(uuid.uuid4()), **(meta or {})}
    return JSONResponse(status_code=status, content={"data": data, "meta": meta, "error": error})


def create_app(agent: ServiceAgent | None = None) -> FastAPI:
    agent = agent or ServiceAgent.from_settings(load_settings())
    app = FastAPI(title="Empório da Música service agent")
    # One turn at a time per conversation, since a turn rewrites that conversation's history.
    session_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    @app.exception_handler(RequestValidationError)
    def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        return _envelope(error={"code": "INVALID_REQUEST", "message": detail}, status=422)

    @app.get("/", include_in_schema=False)
    def chat_page() -> FileResponse:
        return FileResponse(CHAT_PAGE)

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        return _envelope(data={"status": "ok"})

    @app.post("/api/v1/chat")
    def chat(request: ChatRequest) -> JSONResponse:
        session_id = request.session_id or uuid.uuid4().hex[:12]
        with session_locks[session_id]:
            reply = agent.reply(session_id, request.message)
        return _envelope(
            data={"session_id": session_id, "reply": reply.text},
            meta={
                "tools": [t["tool"] for t in reply.tools_used],
                "latency_ms": reply.latency_ms,
                "degraded": reply.degraded,
            },
        )

    return app
