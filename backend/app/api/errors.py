"""Manejo centralizado de errores.

Todas las respuestas de error tienen la misma forma y ninguna incluye traza
interna. El request_id permite correlacionar con los logs sin exponer nada.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.platform.errors import PayCoreError
from app.platform.logging import request_id_var

logger = logging.getLogger(__name__)


def error_body(
    code: str, message: str, details: dict | None = None
) -> dict[str, dict]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(),
            "details": details or {},
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PayCoreError)
    async def _domain_error(_: Request, exc: PayCoreError) -> JSONResponse:
        logger.info("error_de_dominio", extra={"code": exc.code})
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        campos = [
            {"campo": ".".join(str(p) for p in err["loc"][1:]), "motivo": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body(
                "validation_error", "La petición no es válida.", {"campos": campos}
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigos = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                codigos.get(exc.status_code, "http_error"), str(exc.detail)
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Se registra con traza en el log, nunca en la respuesta.
        logger.exception("error_no_controlado", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("internal_error", "Ha ocurrido un error inesperado."),
        )
