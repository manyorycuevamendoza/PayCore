"""Las migraciones son reversibles y el esquema migrado coincide con los modelos."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine

from app.models import Base
from tests.conftest import BACKEND, TEST_URL

pytestmark = pytest.mark.integration


def _alembic(*argumentos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=BACKEND,
        env={**os.environ, "PAYCORE_DATABASE_URL": TEST_URL},
        capture_output=True,
        text=True,
    )


def test_el_esquema_migrado_coincide_con_los_modelos(engine: Engine) -> None:
    """Si alguien cambia un modelo y olvida la migración, esta prueba lo caza."""
    with engine.connect() as conn:
        contexto = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": True}
        )
        diferencias = compare_metadata(contexto, Base.metadata)
    assert diferencias == [], f"El esquema y los modelos divergen: {diferencias}"


def test_la_migracion_es_reversible(engine: Engine) -> None:
    """downgrade base deja la base limpia y upgrade head la reconstruye."""
    engine.dispose()

    abajo = _alembic("downgrade", "base")
    assert abajo.returncode == 0, abajo.stderr

    arriba = _alembic("upgrade", "head")
    assert arriba.returncode == 0, arriba.stderr

    from sqlalchemy import inspect

    tablas = set(inspect(engine).get_table_names())
    assert {"users", "accounts", "transfers", "ledger_entries", "idempotency_keys"} <= tablas
