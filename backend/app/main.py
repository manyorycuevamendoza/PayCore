"""Punto de entrada de la API de PayCore.

PayCore es un prototipo educativo. El saldo es simulado y no existe conexión
con ninguna entidad financiera.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1 import health
from app.api.v1.router import api_router
from app.platform.config import get_settings
from app.platform.logging import configure_logging

DESCRIPCION = """
Motor transaccional de una billetera digital **simulada**.

Prototipo educativo. Los fondos son ficticios y se expresan en soles peruanos
simulados (PEN). No se conecta con Yape, con Credicorp, con entidades
bancarias ni con pasarelas de pago, y no mueve dinero real.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PayCore API",
        description=DESCRIPCION,
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Idempotent-Replay"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    # Solo la sonda de salud se expone sin versionar, para el healthcheck de
    # Compose y de los orquestadores. El resto de la API vive siempre bajo
    # /api/v1, para que el inventario de endpoints sea explícito (API9:2023).
    app.include_router(health.router, include_in_schema=False)

    return app


app = create_app()
