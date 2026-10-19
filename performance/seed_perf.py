"""Prepara el escenario de carga: cuentas ficticias con saldo.

Separado de scripts/seed.py porque las necesidades son distintas: aquí hacen
falta muchas cuentas y saldos grandes para que la carga no se detenga por
fondos insuficientes, salvo en el escenario que precisamente busca eso.

Uso:
    PYTHONPATH=backend python performance/seed_perf.py [numero_de_cuentas]
"""

from __future__ import annotations

import json
import pathlib
import sys

from sqlalchemy import select

from app.modules.accounts.models import Account
from app.modules.identity import service as identity_service
from app.modules.transfers import service as transfers_service
from app.platform.db import unit_of_work

CONTRASENA = "CargaPayCore2026"
SALDO_INICIAL_CENTS = 10_000_000_00  # S/ 10 000 000 simulados, para no agotarlo
PREFIJO = "carga"

# Cuenta única sobre la que todas las peticiones compiten en el escenario de
# contención máxima.
ALIAS_CALIENTE = "cuenta-caliente"

DESTINO = pathlib.Path(__file__).parent / "cuentas.json"


def crear(alias: str, nombre: str, saldo_cents: int) -> dict[str, str]:
    with unit_of_work() as session:
        existente = session.execute(
            select(Account).where(Account.alias == alias)
        ).scalar_one_or_none()
        if existente is None:
            _, cuenta = identity_service.register(
                session,
                email=f"{alias}@carga.pe",
                password=CONTRASENA,
                full_name=nombre,
                alias=alias,
            )
            transfers_service.fund_account(
                session, destination=cuenta, amount_cents=saldo_cents
            )
    return {"alias": alias, "email": f"{alias}@carga.pe", "password": CONTRASENA}


def main() -> int:
    cuantas = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    cuentas = [
        crear(f"{PREFIJO}{i:03d}", f"Cuenta de carga {i}", SALDO_INICIAL_CENTS)
        for i in range(cuantas)
    ]
    caliente = crear(ALIAS_CALIENTE, "Cuenta caliente", SALDO_INICIAL_CENTS)

    DESTINO.write_text(
        json.dumps({"cuentas": cuentas, "caliente": caliente}, indent=2) + "\n"
    )
    print(f"{cuantas} cuentas de carga y una cuenta caliente listas.")
    print(f"Credenciales escritas en {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
