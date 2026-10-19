"""Motor, sesiones y unidad de trabajo.

La unidad de trabajo es el límite transaccional de PayCore: un caso de uso
abre una transacción y la confirma una sola vez. Ver ADR-0005 y ADR-0006.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.platform.config import ConcurrencyStrategy, get_settings
from app.platform.errors import ConcurrencyRetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# SQLSTATE que PostgreSQL devuelve siempre ante un fallo de serialización.
SERIALIZATION_FAILURE = "40001"
# Deadlock. No se reintenta a propósito: el orden determinista de bloqueo de
# ADR-0005 debe hacerlo imposible, y reintentarlo ocultaría el fallo.
DEADLOCK_DETECTED = "40P01"


def sqlstate(error: BaseException) -> str | None:
    """Extrae el SQLSTATE del error original de psycopg, si lo hay."""
    return getattr(getattr(error, "orig", None), "sqlstate", None)


class Base(DeclarativeBase):
    """Base declarativa compartida por todos los módulos."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            echo=settings.db_echo,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _session_factory


def reset_engine() -> None:
    """Descarta motor y fábrica. Lo usan las pruebas al cambiar de base."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def unit_of_work(
    strategy: ConcurrencyStrategy | None = None,
) -> Iterator[Session]:
    """Abre una transacción, la confirma al salir y la deshace ante cualquier error.

    Cuando la estrategia es SERIALIZABLE se fija el nivel de aislamiento en la
    conexión antes de emitir la primera sentencia.
    """
    settings = get_settings()
    effective = strategy or settings.concurrency_strategy
    session = get_session_factory()()
    try:
        if effective == ConcurrencyStrategy.SERIALIZABLE:
            session.connection(
                execution_options={"isolation_level": "SERIALIZABLE"}
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def transactional(
    operation: Callable[[Session], T],
    *,
    strategy: ConcurrencyStrategy | None = None,
) -> T:
    """Ejecuta una operación dentro de una transacción, con reintento si procede.

    En modo SERIALIZABLE, PostgreSQL puede abortar la transacción con SQLSTATE
    40001 cuando detecta dependencias peligrosas de lectura y escritura. Su
    documentación indica expresamente que la aplicación debe tener una forma
    generalizada de manejar ese fallo reintentando la transacción completa.
    Esto es esa forma generalizada.

    El backoff es exponencial con jitter aleatorio para no sincronizar los
    reintentos de todos los clientes tras un pico de contención.
    """
    settings = get_settings()
    efectiva = strategy or settings.concurrency_strategy
    intentos = (
        settings.serializable_max_retries
        if efectiva == ConcurrencyStrategy.SERIALIZABLE
        else 1
    )

    for intento in range(1, intentos + 1):
        try:
            with unit_of_work(efectiva) as session:
                return operation(session)
        except DBAPIError as error:
            estado = sqlstate(error)
            if estado == DEADLOCK_DETECTED:
                # No se reintenta: es un fallo de diseño del orden de bloqueo.
                logger.error("deadlock_detectado", extra={"sqlstate": estado})
                raise
            if estado != SERIALIZATION_FAILURE or intento == intentos:
                if estado == SERIALIZATION_FAILURE:
                    logger.warning(
                        "reintentos_agotados",
                        extra={"sqlstate": estado, "intentos": intentos},
                    )
                    raise ConcurrencyRetryExhaustedError() from error
                raise
            espera = (0.01 * 2 ** (intento - 1)) + random.uniform(0, 0.01)
            logger.info(
                "reintento_por_fallo_de_serializacion",
                extra={"intento": intento, "espera_s": round(espera, 4)},
            )
            time.sleep(espera)

    raise ConcurrencyRetryExhaustedError()


def get_db_session() -> Iterator[Session]:
    """Dependencia de FastAPI para endpoints de solo lectura."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
