"""Punto de entrada de la API de PayCore.

PayCore es un prototipo educativo. El saldo es simulado y no existe conexión
con ninguna entidad financiera.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
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


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Alinea la concurrencia de peticiones con el pool de conexiones.

    Los endpoints son síncronos, así que Starlette los ejecuta en el grupo de
    hilos de AnyIO, que por defecto admite 40 a la vez. Si ese número es mayor
    que las conexiones que el pool puede entregar, el exceso de peticiones se
    queda esperando una conexión y acaba fallando por tiempo de espera.

    Esto no es teórico: con el valor por defecto, la carga de solo lectura
    producía errores `QueuePool limit of size 10 overflow 10 reached,
    connection timed out, timeout 30.00` y latencias de 30 segundos en el
    percentil 98. La medición está en docs/performance.md.

    Igualando el límite de hilos a la capacidad del pool, el exceso espera en
    una cola barata dentro del proceso en lugar de competir por conexiones.
    """
    settings = get_settings()
    limitador = anyio.to_thread.current_default_thread_limiter()
    limitador.total_tokens = settings.db_max_connections
    logger.info(
        "concurrencia_alineada",
        extra={
            "hilos_maximos": settings.db_max_connections,
            "pool": settings.db_pool_size,
            "overflow": settings.db_max_overflow,
        },
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        lifespan=lifespan,
        title="PayCore API",
        description=DESCRIPCION,
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
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
