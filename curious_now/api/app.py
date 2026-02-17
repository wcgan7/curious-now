from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from curious_now.api.routes_stage1 import router as stage1_router
from curious_now.api.routes_stage2 import router as stage2_router
from curious_now.api.routes_stage3_4 import router as stage3_4_router
from curious_now.api.routes_stage7 import router as stage7_router
from curious_now.api.routes_stage8 import router as stage8_router
from curious_now.api.routes_stage9 import router as stage9_router
from curious_now.api.routes_stage10 import router as stage10_router
from curious_now.db import DB
from curious_now.logging_config import setup_logging
from curious_now.metrics import MetricsMiddleware
from curious_now.settings import get_settings

logger = logging.getLogger(__name__)

# Initialize logging
settings = get_settings()
setup_logging(log_format=settings.log_format, log_level=settings.log_level)


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    runtime_settings = get_settings()
    db = DB(
        runtime_settings.database_url,
        pool_enabled=runtime_settings.db_pool_enabled,
        pool_min_size=runtime_settings.db_pool_min_size,
        pool_max_size=runtime_settings.db_pool_max_size,
        pool_timeout_seconds=runtime_settings.db_pool_timeout_seconds,
        statement_timeout_ms=runtime_settings.statement_timeout_ms,
    )
    if runtime_settings.db_pool_enabled:
        db.open_pool()
    app_instance.state.db = db
    try:
        yield
    finally:
        db.close_pool()


app = FastAPI(title="Curious Now API", version="0.1", lifespan=lifespan)


def _build_cors_origins() -> list[str]:
    defaults = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
        "https://curious.now",
        "https://www.curious.now",
        "https://staging.curious.now",
    ]

    dynamic = [settings.public_app_base_url] if settings.public_app_base_url else []
    extras = [
        origin.strip()
        for origin in (settings.cors_allowed_origins or "").split(",")
        if origin.strip()
    ]
    # Preserve order while deduplicating.
    return list(dict.fromkeys(defaults + dynamic + extras))


cors_origins = _build_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "ETag", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# Metrics middleware
app.add_middleware(MetricsMiddleware)


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return str(uuid4())


@app.middleware("http")
async def add_response_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers.setdefault("X-Request-ID", request_id)

    runtime_settings = get_settings()
    if runtime_settings.security_headers_enabled:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    return response


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = _request_id(request)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    logger.warning(
        "HTTP exception %s %s status=%s request_id=%s",
        request.method,
        request.url.path,
        exc.status_code,
        request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {"code": "http_error", "message": message, "request_id": request_id},
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _request_id(request)
    logger.warning(
        "Validation error %s %s request_id=%s",
        request.method,
        request.url.path,
        request_id,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": request_id,
            },
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception(
        "Unhandled exception %s %s request_id=%s",
        request.method,
        request.url.path,
        request_id,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": request_id,
            },
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    runtime_db = getattr(request.app.state, "db", None)
    if isinstance(runtime_db, DB) and runtime_db.is_ready():
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="Not ready")


app.include_router(stage1_router, prefix="/v1")
app.include_router(stage2_router, prefix="/v1")
app.include_router(stage3_4_router, prefix="/v1")
app.include_router(stage7_router, prefix="/v1")
app.include_router(stage8_router, prefix="/v1")
app.include_router(stage9_router, prefix="/v1")
app.include_router(stage10_router, prefix="/v1")
