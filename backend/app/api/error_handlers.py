import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ErrorCode, error_envelope
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            extra={"error_code": exc.code.value, "detail": exc.message},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, request_id_var.get(), exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info("validation_error", extra={"errors": exc.errors()})

        def _safe(err: dict) -> dict:
            ctx = err.get("ctx") or {}
            cleaned = {
                k: str(v) if not isinstance(v, (dict, list, bool, int, float, str, type(None))) else v
                for k, v in ctx.items()
            }
            return {**err, "ctx": cleaned}

        return JSONResponse(
            status_code=422,
            content=error_envelope(
                ErrorCode.VALIDATION_ERROR,
                "Request validation failed",
                request_id_var.get(),
                {"errors": [_safe(e) for e in exc.errors()]},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                request_id_var.get(),
            ),
        )