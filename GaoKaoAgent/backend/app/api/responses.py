import logging

import pymysql
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def success(data, *, status: int = 200, meta: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder({"code": "OK", "message": "success", "data": data, "meta": meta}),
    )


def error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder({"code": code, "message": message, "data": None, "meta": details}),
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
            for item in exc.errors()
        ]
        return error(422, "VALIDATION_ERROR", "Invalid request", {"fields": fields})

    @app.exception_handler(HTTPException)
    async def http_handler(_request: Request, exc: HTTPException):
        return error(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(pymysql.MySQLError)
    async def database_handler(_request: Request, exc: pymysql.MySQLError):
        logger.exception("Database operation failed: %s", type(exc).__name__)
        return error(503, "DATABASE_ERROR", "Database operation unavailable")

    @app.exception_handler(Exception)
    async def unknown_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled request failure")
        return error(500, "INTERNAL_ERROR", "Internal server error")

