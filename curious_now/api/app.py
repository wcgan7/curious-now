from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from curious_now.api.routes_stage1 import router as stage1_router
from curious_now.api.routes_stage2 import router as stage2_router
from curious_now.api.routes_stage3_4 import router as stage3_4_router
from curious_now.api.routes_stage5 import router as stage5_router
from curious_now.api.routes_stage6 import router as stage6_router
from curious_now.api.routes_stage7 import router as stage7_router
from curious_now.api.routes_stage8 import router as stage8_router
from curious_now.api.routes_stage9 import router as stage9_router
from curious_now.api.routes_stage10 import router as stage10_router
from curious_now.logging_config import setup_logging
from curious_now.metrics import MetricsMiddleware
from curious_now.settings import get_settings

# Initialize logging
settings = get_settings()
setup_logging(log_format=settings.log_format, log_level=settings.log_level)

app = FastAPI(title="Curious Now API", version="0.1")

# CORS configuration
cors_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://curious.now",
    "https://www.curious.now",
    "https://staging.curious.now",
]

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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(stage1_router, prefix="/v1")
app.include_router(stage2_router, prefix="/v1")
app.include_router(stage3_4_router, prefix="/v1")
app.include_router(stage5_router, prefix="/v1")
app.include_router(stage6_router, prefix="/v1")
app.include_router(stage7_router, prefix="/v1")
app.include_router(stage8_router, prefix="/v1")
app.include_router(stage9_router, prefix="/v1")
app.include_router(stage10_router, prefix="/v1")
