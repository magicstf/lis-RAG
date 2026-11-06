from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Business error that maps directly onto the unified response envelope."""

    http_status = 400

    def __init__(self, message: str, *, code: int | None = None, detail: Any = None, http_status: int | None = None):
        super().__init__(message)
        self.message = message
        self.http_status = http_status or self.__class__.http_status
        self.code = code if code is not None else self.http_status
        self.detail = detail


class BadRequest(AppError):
    http_status = 400


class NotFound(AppError):
    http_status = 404


class UnprocessableFile(AppError):
    http_status = 422


class UpstreamError(AppError):
    http_status = 502


class UpstreamTimeout(AppError):
    http_status = 504


def ok(data: Any = None, status_code: int = 200, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"code": 0, "data": data, "message": "ok"}, status_code=status_code, headers=headers)


def fail(code: int, message: str, detail: Any = None, status_code: int | None = None) -> JSONResponse:
    return JSONResponse(
        {"code": code, "message": message, "detail": detail},
        status_code=status_code or code,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return fail(exc.code, exc.message, exc.detail, exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return fail(400, "请求参数不合法", exc.errors(), 400)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        message = "资源不存在" if exc.status_code == 404 else str(exc.detail)
        return fail(exc.status_code, message, None, exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return fail(500, "服务内部错误", f"{type(exc).__name__}: {exc}", 500)
