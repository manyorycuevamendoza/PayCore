"""Motor, sesiones y unidad de trabajo.

La unidad de trabajo es el límite transaccional de PayCore: un caso de uso
abre una transacción y la confirma una sola vez. Ver ADR-0005 y ADR-0006.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.platform.config import ConcurrencyStrategy, get_settings


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


def get_db_session() -> Iterator[Session]:
    """Dependencia de FastAPI para endpoints de solo lectura."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
