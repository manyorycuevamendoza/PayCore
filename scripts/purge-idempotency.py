"""Elimina las claves de idempotencia caducadas (TTL de 24 h por defecto).

No es un trabajo en segundo plano: añadir un planificador al MVP no está
justificado. Se ejecuta a mano o desde cron. Ver ADR-0006.

Uso:
    PYTHONPATH=backend python scripts/purge-idempotency.py
"""

from __future__ import annotations

import sys

from app.modules.idempotency import service as idempotency_service
from app.platform.db import unit_of_work


def main() -> int:
    with unit_of_work() as session:
        borradas = idempotency_service.purge_expired(session)
    print(f"Claves de idempotencia caducadas eliminadas: {borradas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
