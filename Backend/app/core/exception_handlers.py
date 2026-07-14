"""
app/core/exception_handlers.py

Global FastAPI exception handlers.

Rules:
  - Never expose raw exception messages to clients in production.
  - Always log the full exception server-side for debugging.
  - Use structured logging (logger.error / logger.warning) — never print().
"""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handles HTTP 404 and other HTTPExceptions registered via add_exception_handler."""
    logger.warning(
        "HTTP error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Not Found"},
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handles Pydantic request-body validation errors (HTTP 422)."""
    logger.info(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Pydantic error dicts are safe to return — they describe request fields
        # the client controls, not server internals.
        content={"detail": exc.errors()},
    )


def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """
    Handles unexpected database errors.

    The raw SQLAlchemy error is logged server-side but NEVER sent to the client —
    it can contain table names, column names, or constraint details.
    """
    logger.error(
        "Database error on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,   # includes full traceback in log
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred. Please try again."},
    )


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unhandled exceptions.

    Logs the full traceback. Clients receive a generic message with no
    internal details.
    """
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )
