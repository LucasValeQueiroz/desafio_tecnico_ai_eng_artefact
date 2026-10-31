"""Thin HTTP interface over the agent. All responses use the { data, meta, error } envelope."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent import MAX_MESSAGE_CHARS, ServiceAgent
from .config import ConfigError, load_settings

logger = logging.getLogger(__name__)

CHAT_PAGE = Path(__file__).parent / "static" / "index.html"
MINUTE_SECONDS = 60
DAY_SECONDS = 86400
RATE_LIMITED_MESSAGE = "Muitas mensagens em pouco tempo. Aguarde um instante e tente de novo."


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class RateLimiter:
    """Limits messages per client and overall, protecting the paid key behind a public URL.

    The counters live in the process, so on serverless they apply per instance. This slows down
    casual abuse. Simultaneous requests can reach separate instances, so the real ceiling lives outside the application (ADR-006).
    """

    def __init__(self, per_minute: int = 10, per_day: int = 300, clock=time.monotonic) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._lock = threading.Lock()
        self._by_client: defaultdict[str, deque[float]] = defaultdict(deque)
        self._all: deque[float] = deque()

    def allow(self, client: str) -> bool:
        now = self._clock()
        with self._lock:
            while self._all and now - self._all[0] >= DAY_SECONDS:
                self._all.popleft()
            recent = self._by_client[client]
            while recent and now - recent[0] >= MINUTE_SECONDS:
                recent.popleft()
            if len(recent) >= self._per_minute or len(self._all) >= self._per_day:
                return False
            recent.append(now)
            self._all.append(now)
            return True


def _client_address(request: Request) -> str:
    # The platform's proxy sets this header. Without a proxy, the socket address is used.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _envelope(data=None, meta: dict | None = None, error: dict | None = None, status: int = 200) -> JSONResponse:
    meta = {"request_id": str(uuid.uuid4()), **(meta or {})}
    return JSONResponse(status_code=status, content={"data": data, "meta": meta, "error": error})


def _new_app() -> FastAPI:
    return FastAPI(title="Empório da Música service agent", docs_url=None, redoc_url=None, openapi_url=None)


def _unavailable_app(code: str, message: str) -> FastAPI:
    """Answers every request with the reason, since a crash at import shows only an opaque platform error."""
    app = _new_app()

    @app.api_route("/{path:path}", methods=["GET", "POST"], include_in_schema=False)
    def unavailable(path: str) -> JSONResponse:
        return _envelope(error={"code": code, "message": message}, status=503)

    return app


def create_app(agent: ServiceAgent | None = None, limiter: RateLimiter | None = None) -> FastAPI:
    if agent is None:
        try:
            settings = load_settings()
            agent = ServiceAgent.from_settings(settings)
        except ConfigError as error:
            logger.error("Agent not configured: %s", error)
            return _unavailable_app("NOT_CONFIGURED", str(error))
        except OSError as error:
            logger.exception("Agent failed to start")
            missing = Path(error.filename).name if error.filename else "unknown"
            return _unavailable_app("STARTUP_FAILED", f"{type(error).__name__}: {missing}")
        limiter = limiter or RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_per_day)
    limiter = limiter or RateLimiter()

    app = _new_app()
    # One turn at a time per conversation, since a turn rewrites that conversation's history.
    session_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    @app.exception_handler(RequestValidationError)
    def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        return _envelope(error={"code": "INVALID_REQUEST", "message": detail}, status=422)

    @app.exception_handler(StarletteHTTPException)
    def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        return _envelope(error={"code": "HTTP_ERROR", "message": str(error.detail)}, status=error.status_code)

    @app.get("/", include_in_schema=False)
    def chat_page() -> FileResponse:
        return FileResponse(CHAT_PAGE)

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        return _envelope(data={"status": "ok"})

    @app.post("/api/v1/chat")
    def chat(body: ChatRequest, request: Request) -> JSONResponse:
        if not limiter.allow(_client_address(request)):
            return _envelope(error={"code": "RATE_LIMITED", "message": RATE_LIMITED_MESSAGE}, status=429)
        session_id = body.session_id or uuid.uuid4().hex[:12]
        with session_locks[session_id]:
            reply = agent.reply(session_id, body.message)
        return _envelope(
            data={"session_id": session_id, "reply": reply.text},
            meta={
                "tools": [t["tool"] for t in reply.tools_used],
                "latency_ms": reply.latency_ms,
                "degraded": reply.degraded,
            },
        )

    return app
