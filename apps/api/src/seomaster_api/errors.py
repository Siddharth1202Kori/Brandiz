"""One error shape for every failure: {"error": {"code", "message", "details"?}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from seomaster_providers.dal import BudgetExceededError
from seomaster_providers.dataforseo.client import (
    DataForSEOAuthError,
    DataForSEOError,
    DataForSEOPaymentError,
)

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


class QuotaExceededError(AppError):
    def __init__(self, metric: str, limit: int) -> None:
        super().__init__(
            429,
            "quota_exceeded",
            f"Plan limit reached for {metric}",
            {"metric": metric, "limit": limit},
        )


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(BudgetExceededError)
    async def _budget(_: Request, exc: BudgetExceededError) -> JSONResponse:
        return error_response(
            503,
            "budget_exceeded",
            "Data temporarily unavailable, try again later",
            {"scope": exc.scope},
        )

    @app.exception_handler(DataForSEOError)
    async def _provider(_: Request, exc: DataForSEOError) -> JSONResponse:
        # Auth/balance problems are ours to fix, not the user's: log loudly, answer generically.
        level = (
            logging.ERROR
            if isinstance(exc, DataForSEOAuthError | DataForSEOPaymentError)
            else logging.WARNING
        )
        log.log(level, "provider error: %s", exc)
        return error_response(
            502, "provider_error", "Keyword data provider failed, try again shortly"
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", "Invalid request", {"errors": exc.errors()})
