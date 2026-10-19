"""Infraestructura común de pruebas.

Las pruebas corren contra un PostgreSQL real, no contra SQLite: lo que se está
verificando son garantías del motor (CHECK, triggers, bloqueos, niveles de
aislamiento) que un motor distinto no reproduce.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
BACKEND = RAIZ / "backend"

ADMIN_URL = os.getenv(
    "PAYCORE_TEST_ADMIN_URL",
    "postgresql+psycopg://paycore:paycore@localhost:5434/postgres",
)
TEST_DB = os.getenv("PAYCORE_TEST_DB", "paycore_test")
TEST_URL = os.getenv(
    "PAYCORE_TEST_DATABASE_URL",
    f"postgresql+psycopg://paycore:paycore@localhost:5434/{TEST_DB}",
)

TABLAS = ("idempotency_keys", "ledger_entries", "transfers", "accounts", "users")


def _recrear_base() -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": TEST_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()


def _migrar() -> None:
    entorno = {**os.environ, "PAYCORE_DATABASE_URL": TEST_URL}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=entorno,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head falló:\n{resultado.stdout}\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _recrear_base()
    _migrar()
    motor = create_engine(TEST_URL, future=True)
    yield motor
    motor.dispose()


@pytest.fixture
def limpiar(engine: Engine) -> Iterator[None]:
    """Deja la base vacía antes de cada prueba.

    Se usa TRUNCATE y no DELETE porque el ledger es de solo inserción: el
    trigger trg_ledger_append_only rechaza cualquier DELETE sobre sus filas.
    """
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session(engine: Engine, limpiar: None) -> Iterator[Session]:
    fabrica = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with fabrica() as s:
        yield s


# --- Ayudantes para construir datos ficticios -------------------------------


def crear_usuario(conn, email: str | None = None, nombre: str = "Persona Ficticia") -> uuid.UUID:
    email = email or f"{uuid.uuid4().hex[:12]}@ejemplo.test"
    return conn.execute(
        text(
            "INSERT INTO users (email, password_hash, full_name) "
            "VALUES (:email, 'hash-ficticio', :nombre) RETURNING id"
        ),
        {"email": email, "nombre": nombre},
    ).scalar_one()


def crear_cuenta(
    conn,
    user_id: uuid.UUID | None,
    alias: str,
    balance_cents: int = 0,
    kind: str = "user",
) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO accounts (user_id, alias, kind, balance_cents) "
            "VALUES (:user_id, :alias, :kind, :balance) RETURNING id"
        ),
        {"user_id": user_id, "alias": alias, "kind": kind, "balance": balance_cents},
    ).scalar_one()


def crear_transferencia(
    conn,
    origen: uuid.UUID,
    destino: uuid.UUID,
    amount_cents: int,
    status: str = "completed",
) -> uuid.UUID:
    completed_at = "now()" if status == "completed" else "NULL"
    motivo = "'insufficient_funds'" if status == "rejected" else "NULL"
    return conn.execute(
        text(
            "INSERT INTO transfers "
            "(source_account_id, destination_account_id, amount_cents, status, "
            f" completed_at, rejection_reason) "
            f"VALUES (:origen, :destino, :importe, :status, {completed_at}, {motivo}) "
            "RETURNING id"
        ),
        {"origen": origen, "destino": destino, "importe": amount_cents, "status": status},
    ).scalar_one()


def crear_asiento(
    conn,
    transfer_id: uuid.UUID,
    account_id: uuid.UUID,
    amount_cents: int,
    balance_after_cents: int = 0,
) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO ledger_entries "
            "(transfer_id, account_id, amount_cents, balance_after_cents) "
            "VALUES (:t, :a, :importe, :saldo) RETURNING id"
        ),
        {
            "t": transfer_id,
            "a": account_id,
            "importe": amount_cents,
            "saldo": balance_after_cents,
        },
    ).scalar_one()
