"""
error_handlers.py -- Global FastAPI exception handlers
Import this in main.py and call register_exception_handlers(app) after app creation.
"""

import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from bili_exceptions import (
    BiliSumException,
    APIError,
    AIError,
    DatabaseError,
    ValidationError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    EmbeddingError,
    SubtitleError,
    ExportError,
    ConfigurationError,
    ServiceUnavailableError,
    TimeoutError,
)

logger = logging.getLogger("bilisum.error_handlers")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_trace_id(request: Request) -> str:
    """Extract or generate a trace-id for this request.

    Priority: X-Trace-Id header > X-Request-Id header > auto-generated UUID.
    """
    for header_name in ("X-Trace-Id", "X-Request-Id"):
        value = request.headers.get(header_name)
        if value:
            return value
    return uuid.uuid4().hex[:16]


def _request_context(request: Request) -> dict:
    """Build a dict of request-scoped metadata for structured logging."""
    return {
        "method": request.method,
        "path": request.url.path,
        "client": request.client.host if request.client else "unknown",
    }


def _error_response(exc: BiliSumException, trace_id: str = "") -> JSONResponse:
    """Convert a BiliSumException to a standardized JSON error response.

    Uses BiliSumException.to_dict() to build the error payload, then
    injects the trace_id so clients can reference it in bug reports.
    """
    payload: dict = {"error": exc.to_dict()}
    if trace_id:
        payload["error"]["trace_id"] = trace_id
    return JSONResponse(status_code=exc.http_status, content=payload)


def _log_extras(exc: BiliSumException, trace_id: str, ctx: dict) -> dict:
    """Build a structured-extra dict for logger.xxx(..., extra=...)."""
    extra = {
        "error_code": exc.error_code,
        "http_status": exc.http_status,
        "trace_id": trace_id,
        **ctx,
    }
    return extra


# ---------------------------------------------------------------------------
# Per-exception-type handlers
# ---------------------------------------------------------------------------

async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.warning(
        "APIError: %s | bili_code=%s | method=%s path=%s | trace_id=%s",
        exc.message, exc.bili_code, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _ai_error_handler(request: Request, exc: AIError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "AIError: %s | model=%s api_http_status=%s | method=%s path=%s | trace_id=%s",
        exc.message, exc.model, exc.api_http_status, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "DatabaseError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        exc_info=True,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.info(
        "ValidationError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.warning(
        "AuthenticationError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _rate_limit_error_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.warning(
        "RateLimitError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.info(
        "NotFoundError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _embedding_error_handler(request: Request, exc: EmbeddingError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "EmbeddingError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        exc_info=True,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _subtitle_error_handler(request: Request, exc: SubtitleError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.info(
        "SubtitleError: %s | bvid=%s | method=%s path=%s | trace_id=%s",
        exc.message, exc.bvid, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _export_error_handler(request: Request, exc: ExportError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "ExportError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        exc_info=True,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _configuration_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "ConfigurationError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _service_unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "ServiceUnavailableError: %s | method=%s path=%s | trace_id=%s",
        exc.message, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _timeout_error_handler(request: Request, exc: TimeoutError) -> JSONResponse:
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "TimeoutError: %s | service=%s timeout=%ss | method=%s path=%s | trace_id=%s",
        exc.message, exc.service, exc.timeout_seconds, ctx["method"], ctx["path"], trace_id,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _generic_bilisum_exception_handler(request: Request, exc: BiliSumException) -> JSONResponse:
    """Catch-all for BiliSumException subclasses that lack a dedicated handler."""
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    logger.error(
        "BiliSumException (unregistered subtype %s): %s | method=%s path=%s | trace_id=%s",
        exc.__class__.__name__, exc.message, ctx["method"], ctx["path"], trace_id,
        exc_info=True,
        extra=_log_extras(exc, trace_id, ctx),
    )
    return _error_response(exc, trace_id)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Final fallback: catch all Python exceptions not matched above.

    In production, never leak exc.__class__.__name__ or str(exc) to the client.
    Detail is only included in debug mode.
    """
    import os
    import time as _time
    trace_id = _get_trace_id(request)
    ctx = _request_context(request)
    is_debug = os.getenv("BILISUM_DEBUG", "0") == "1"
    logger.critical(
        "Unhandled Exception: %s: %s | method=%s path=%s | trace_id=%s",
        exc.__class__.__name__, exc, ctx["method"], ctx["path"], trace_id,
        exc_info=True,
        extra={"trace_id": trace_id, **ctx},
    )
    payload: dict = {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误，请稍后重试",
            "timestamp": _time.time(),
        }
    }
    if trace_id:
        payload["error"]["trace_id"] = trace_id
    if is_debug:
        payload["error"]["detail"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
    return JSONResponse(status_code=500, content=payload)


# ==================== Pydantic RequestValidationError handler ====================

async def _pydantic_validation_handler(request: Request, exc):
    """Convert FastAPI/Pydantic RequestValidationError to standardized format."""
    from fastapi.exceptions import RequestValidationError
    if isinstance(exc, RequestValidationError):
        import time as _time
        trace_id = _get_trace_id(request)
        ctx = _request_context(request)
        errors = exc.errors()
        logger.info(
            "RequestValidationError: %d error(s) | method=%s path=%s | trace_id=%s",
            len(errors), ctx["method"], ctx["path"], trace_id,
            extra={"trace_id": trace_id, **ctx},
        )
        payload = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数验证失败",
                "timestamp": _time.time(),
                "trace_id": trace_id,
                "detail": [
                    {
                        "field": ".".join(str(loc) for loc in e["loc"]),
                        "message": e["msg"],
                        "type": e["type"],
                    }
                    for e in errors
                ],
            }
        }
        return JSONResponse(status_code=422, content=payload)
    return await _unhandled_exception_handler(request, exc)


# ==================== FastAPI HTTPException handler ====================

async def _http_exception_handler(request: Request, exc):
    """Convert FastAPI built-in HTTPException to standardized format."""
    from fastapi.exceptions import HTTPException as FastAPIHTTPException
    if isinstance(exc, FastAPIHTTPException):
        import time as _time
        trace_id = _get_trace_id(request)
        ctx = _request_context(request)
        logger.info(
            "HTTPException: %d - %s | method=%s path=%s | trace_id=%s",
            exc.status_code, exc.detail, ctx["method"], ctx["path"], trace_id,
            extra={"trace_id": trace_id, **ctx},
        )
        payload = {
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "timestamp": _time.time(),
                "trace_id": trace_id,
            }
        }
        return JSONResponse(status_code=exc.status_code, content=payload)
    return await _unhandled_exception_handler(request, exc)


# ==================== Registration ====================

def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app.

    Usage:
        from error_handlers import register_exception_handlers
        app = FastAPI()
        register_exception_handlers(app)
    """
    from fastapi.exceptions import HTTPException as FastAPIHTTPException
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(AIError, _ai_error_handler)
    app.add_exception_handler(DatabaseError, _database_error_handler)
    app.add_exception_handler(ValidationError, _validation_error_handler)
    app.add_exception_handler(AuthenticationError, _authentication_error_handler)
    app.add_exception_handler(RateLimitError, _rate_limit_error_handler)
    app.add_exception_handler(NotFoundError, _not_found_error_handler)
    app.add_exception_handler(EmbeddingError, _embedding_error_handler)
    app.add_exception_handler(SubtitleError, _subtitle_error_handler)
    app.add_exception_handler(ExportError, _export_error_handler)
    app.add_exception_handler(ConfigurationError, _configuration_error_handler)
    app.add_exception_handler(ServiceUnavailableError, _service_unavailable_handler)
    app.add_exception_handler(TimeoutError, _timeout_error_handler)
    app.add_exception_handler(BiliSumException, _generic_bilisum_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _pydantic_validation_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    logger.info(
        "Global exception handlers registered (14 custom + HTTP + Pydantic + fallback)"
    )


# Backward-compatible alias (main.py calls register_error_handlers)
register_error_handlers = register_exception_handlers
