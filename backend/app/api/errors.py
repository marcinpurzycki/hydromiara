"""Uniform error body: {"code": ..., "message": <Polish text>}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.contracts.common import ErrorResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_responses(*status_codes: int) -> dict[int | str, dict]:
    """OpenAPI declaration of error responses for a route."""
    return {code: {"model": ErrorResponse} for code in status_codes}


_HTTP_MESSAGES = {
    404: ("not_found", "Nie znaleziono zasobu."),
    405: ("method_not_allowed", "Niedozwolona metoda dla tego adresu."),
}


def _body(code: str, message: str) -> dict:
    return ErrorResponse(code=code, message=message).model_dump()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({str(error["loc"][-1]) for error in exc.errors() if error["loc"]})
        message = "Nieprawidłowe dane żądania."
        if fields:
            message = f"Nieprawidłowe dane żądania: {', '.join(fields)}."
        return JSONResponse(status_code=422, content=_body("validation_error", message))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_MESSAGES.get(exc.status_code, ("http_error", "Błąd żądania."))
        return JSONResponse(status_code=exc.status_code, content=_body(code, message))
