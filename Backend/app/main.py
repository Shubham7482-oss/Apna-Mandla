"""
app/main.py — FastAPI application factory.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.exception_handlers import (
    generic_exception_handler,
    http_exception_handler,
    sqlalchemy_exception_handler,
    validation_exception_handler,
)
from app.routes import udhar_agreement, udhar_transaction
from app.websocket_manager import manager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (DEBUG=%s)", settings.PROJECT_NAME, settings.DEBUG)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema verified.")

    # Start background financial scheduler
    # (daily reconciliation, udhar interest, overdue flagging, OTP cleanup)
    from app.services.scheduled_jobs import start_scheduler
    scheduler = start_scheduler()

    yield

    # Graceful shutdown
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    logger.info("Shutting down %s.", settings.PROJECT_NAME)


# ─────────────────────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url="/docs"   if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY HEADERS MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"]        = "0"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# CORS
# CSRF note: X-CSRF-Token must be in allow_headers so browsers send it.
# ─────────────────────────────────────────────────────────────────────────────

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,   # required for cookies to be sent cross-origin
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-CSRF-Token",       # required for the double-submit CSRF pattern
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    logger.info("CORS enabled for origins: %s", settings.CORS_ORIGINS)
else:
    logger.warning(
        "CORS_ORIGINS is empty — cross-origin requests will be blocked. "
        "Set CORS_ORIGINS in .env."
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXCEPTION HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(404, http_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTERS — single mount point; all routes live in api/v1/api.py
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix=settings.API_V1_STR)

app.include_router(
    udhar_agreement.router,
    prefix=settings.API_V1_STR,
    tags=["Udhar Agreements"],
)
app.include_router(
    udhar_transaction.router,
    prefix=settings.API_V1_STR,
    tags=["Udhar Transactions"],
)


# ─────────────────────────────────────────────────────────────────────────────
# STATIC
# ─────────────────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# ROOT + WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Per-user WebSocket. TODO: add token auth before connect()."""
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)
