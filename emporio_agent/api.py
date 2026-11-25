"""Thin HTTP interface over the agent. All responses use the { data, meta, error } envelope."""
from __future__ import annotations

import logging
import secrets
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

from .access import AccessError, AccessStore, FirebaseRTDBAccessStore, InMemoryAccessStore
from .agent import MAX_MESSAGE_CHARS, ServiceAgent
from .config import ConfigError, load_settings
from .notify import EmailNotifier

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
CHAT_PAGE = STATIC_DIR / "index.html"
ADMIN_PAGE = STATIC_DIR / "admin.html"
MINUTE_SECONDS = 60
DAY_SECONDS = 86400
RATE_LIMITED_MESSAGE = "Muitas mensagens em pouco tempo. Aguarde um instante e tente de novo."


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class AccessRequestBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    note: str = Field(default="", max_length=300)


class AccessDecisionBody(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=20)


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


def _extract_access_token(request: Request) -> str:
    header = request.headers.get("x-access-token", "").strip()
    if header:
        return header
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _is_valid_admin(request: Request, admin_token: str | None) -> bool:
    if not admin_token:
        return False
    provided = request.headers.get("x-admin-token", "").strip()
    if not provided:
        return False
    return secrets.compare_digest(provided, admin_token)


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


def create_app(
    agent: ServiceAgent | None = None,
    limiter: RateLimiter | None = None,
    access_store: AccessStore | None = None,
    admin_token: str | None = None,
    approved_emails: set[str] | None = None,
    notifier: EmailNotifier | None = None,
) -> FastAPI:
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
        if access_store is None and settings.access_gate_enabled:
            if settings.firebase_db_url:
                access_store = FirebaseRTDBAccessStore(settings.firebase_db_url, settings.firebase_db_secret)
            else:
                logger.warning("Access gate enabled without FIREBASE_DB_URL; using in-memory store (ephemeral on serverless).")
                access_store = InMemoryAccessStore()
        admin_token = admin_token if admin_token is not None else settings.admin_token
        approved_emails = approved_emails if approved_emails is not None else set(settings.approved_emails)
        if notifier is None and settings.notify_email:
            candidate = EmailNotifier(
                notify_email=settings.notify_email,
                resend_api_key=settings.resend_api_key,
                resend_from=settings.resend_from,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
            )
            if candidate.configured:
                notifier = candidate

    limiter = limiter or RateLimiter()
    approved_set = {email.strip().lower() for email in (approved_emails or set()) if email.strip()}

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

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return FileResponse(ADMIN_PAGE)

    @app.get("/api/v1/health")
    def health() -> JSONResponse:
        return _envelope(data={"status": "ok", "access_gate": access_store is not None, **agent.store_status()})

    @app.get("/api/v1/access/status")
    def access_status(request: Request) -> JSONResponse:
        if access_store is None:
            return _envelope(data={"gate_enabled": False, "status": "approved"})
        token = _extract_access_token(request)
        if not token:
            return _envelope(data={"gate_enabled": True, "status": "none"})
        try:
            record = access_store.get_by_token(token)
        except RuntimeError as error:
            logger.error("Access store error on status check: %s", error)
            return _envelope(error={"code": "ACCESS_STORE_ERROR", "message": "Não foi possível verificar o acesso agora."}, status=503)
        if record is None:
            return _envelope(data={"gate_enabled": True, "status": "none"})
        return _envelope(
            data={
                "gate_enabled": True,
                "status": record.status,
                "name": record.name,
                "email": record.email,
            }
        )

    @app.post("/api/v1/access/request")
    def request_access(body: AccessRequestBody, request: Request) -> JSONResponse:
        if access_store is None:
            return _envelope(data={"gate_enabled": False, "status": "approved"})
        if not limiter.allow(f"access:{_client_address(request)}"):
            return _envelope(error={"code": "RATE_LIMITED", "message": RATE_LIMITED_MESSAGE}, status=429)
        auto_approve = body.email.strip().lower() in approved_set
        try:
            record, expose_token = access_store.request_access(
                name=body.name,
                email=body.email,
                note=body.note,
                auto_approve=auto_approve,
            )
        except AccessError as error:
            return _envelope(error={"code": "INVALID_REQUEST", "message": str(error)}, status=422)
        except RuntimeError as error:
            logger.error("Access store error on request: %s", error)
            return _envelope(error={"code": "ACCESS_STORE_ERROR", "message": "Erro ao registrar solicitação. Tente novamente."}, status=503)
        if notifier is not None and record.status == "pending" and expose_token:
            admin_url = str(request.base_url).rstrip("/") + "/admin"
            notifier.notify_new_request(record.name, record.email, record.note, admin_url=admin_url)
        payload = {"status": record.status, "name": record.name, "email": record.email}
        if expose_token:
            payload["token"] = record.token
        return _envelope(data=payload)

    @app.get("/api/v1/access/admin/requests")
    def admin_list_requests(request: Request) -> JSONResponse:
        if access_store is None:
            return _envelope(error={"code": "NOT_CONFIGURED", "message": "Gate de acesso não está ativo."}, status=400)
        if not _is_valid_admin(request, admin_token):
            return _envelope(error={"code": "UNAUTHORIZED", "message": "Token de administrador inválido."}, status=401)
        try:
            items = [item.public_dict() for item in access_store.list_requests()]
        except RuntimeError as error:
            logger.error("Access store error on admin list: %s", error)
            return _envelope(error={"code": "ACCESS_STORE_ERROR", "message": "Erro ao consultar solicitações."}, status=503)
        return _envelope(data={"requests": items})

    @app.post("/api/v1/access/admin/decision")
    def admin_decide_request(body: AccessDecisionBody, request: Request) -> JSONResponse:
        if access_store is None:
            return _envelope(error={"code": "NOT_CONFIGURED", "message": "Gate de acesso não está ativo."}, status=400)
        if not _is_valid_admin(request, admin_token):
            return _envelope(error={"code": "UNAUTHORIZED", "message": "Token de administrador inválido."}, status=401)
        try:
            updated = access_store.set_status(body.key, body.status.strip().lower())
        except AccessError as error:
            return _envelope(error={"code": "INVALID_REQUEST", "message": str(error)}, status=422)
        except RuntimeError as error:
            logger.error("Access store error on admin decision: %s", error)
            return _envelope(error={"code": "ACCESS_STORE_ERROR", "message": "Erro ao atualizar solicitação."}, status=503)
        if updated is None:
            return _envelope(error={"code": "NOT_FOUND", "message": "Solicitação não encontrada."}, status=404)
        return _envelope(data={"request": updated.public_dict()})

    @app.post("/api/v1/chat")
    def chat(body: ChatRequest, request: Request) -> JSONResponse:
        if access_store is not None:
            token = _extract_access_token(request)
            try:
                record = access_store.get_by_token(token) if token else None
            except RuntimeError as error:
                logger.error("Access store error on chat: %s", error)
                return _envelope(error={"code": "ACCESS_STORE_ERROR", "message": "Não foi possível validar sua autorização."}, status=503)
            if record is None or record.status != "approved":
                return _envelope(
                    error={"code": "ACCESS_REQUIRED", "message": "Acesso pendente ou não aprovado. Solicite liberação para usar o chat."},
                    status=403,
                )

        if not limiter.allow(_client_address(request)):
            return _envelope(error={"code": "RATE_LIMITED", "message": RATE_LIMITED_MESSAGE}, status=429)
        session_id = body.session_id or uuid.uuid4().hex[:12]
        with session_locks[session_id]:
            reply = agent.reply(session_id, body.message)
        return _envelope(
            data={"session_id": session_id, "reply": reply.text},
            meta={
                "tools": [t["tool"] for t in reply.tools_used],
                # Verification factors are already redacted, so this is safe to show on the demo page.
                "consultations": reply.tools_used,
                "checked_values": reply.checked_values,
                "latency_ms": reply.latency_ms,
                "degraded": reply.degraded,
            },
        )

    return app
