"""Carga datos ficticios de prueba.

Crea tres personas con saldo simulado. El saldo NO aparece de la nada: se
acredita desde la cuenta de sistema SYSTEM_FUNDING, que es la única exenta de
la restricción de no negatividad, de modo que la suma global de asientos del
ledger sigue siendo exactamente cero. Ver ADR-0004.

Uso:
    PYTHONPATH=backend python scripts/seed.py
    ./scripts/seed.sh            (dentro del contenedor)
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.modules.accounts.models import SYSTEM_FUNDING_ALIAS, Account
from app.modules.identity import service as identity_service
from app.modules.transfers import service as transfers_service
from app.platform.db import unit_of_work
from app.platform.money import cents_to_display

CONTRASENA_DEMO = "PayCoreDemo2026"

PERSONAS = [
    ("ana", "Ana Quispe", "ana@ejemplo.pe", 100_00),
    ("luis", "Luis Rojas", "luis@ejemplo.pe", 20_00),
    ("rosa", "Rosa Mamani", "rosa@ejemplo.pe", 250_00),
]


def main() -> int:
    creados = []
    with unit_of_work() as session:
        for alias, nombre, email, saldo_cents in PERSONAS:
            existente = session.execute(
                select(Account).where(Account.alias == alias)
            ).scalar_one_or_none()
            if existente is not None:
                print(f"  {alias:6} ya existe, se omite")
                continue

            _, cuenta = identity_service.register(
                session,
                email=email,
                password=CONTRASENA_DEMO,
                full_name=nombre,
                alias=alias,
            )
            transfers_service.fund_account(
                session, destination=cuenta, amount_cents=saldo_cents
            )
            creados.append((alias, email, saldo_cents))

    if not creados:
        print("\nNo había nada que crear.")
        return 0

    print("\nDatos ficticios cargados. Todos los saldos son simulados (PEN).\n")
    print(f"  {'alias':8} {'correo':22} {'saldo':>10}")
    print(f"  {'-' * 8} {'-' * 22} {'-' * 10}")
    for alias, email, saldo in creados:
        print(f"  {alias:8} {email:22} {cents_to_display(saldo):>10}")
    print(f"\n  Contraseña para todas: {CONTRASENA_DEMO}")
    print("\n  El origen del saldo es la cuenta de sistema "
          f"{SYSTEM_FUNDING_ALIAS}, que queda en negativo")
    print("  a propósito para que el ledger siga sumando cero.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
