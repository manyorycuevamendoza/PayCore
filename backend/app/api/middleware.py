"""Middleware de correlación de peticiones."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.platform.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        inicio = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duracion_ms = (time.perf_counter() - inicio) * 1000
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "peticion",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duracion_ms": round(duracion_ms, 2),
                "request_id": request_id,
            },
        )
        return response
