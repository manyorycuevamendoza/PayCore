"""Consulta, bloqueo y financiación de cuentas."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import (
    ACCOUNT_KIND_SYSTEM,
    SYSTEM_FUNDING_ALIAS,
    Account,
)
from app.platform.errors import NotFoundError


def get_by_user(session: Session, user_id: uuid.UUID) -> Account:
    cuenta = session.execute(
        select(Account).where(Account.user_id == user_id)
    ).scalar_one_or_none()
    if cuenta is None:
        raise NotFoundError("La cuenta no existe.")
    return cuenta


def get_by_alias(session: Session, alias: str) -> Account:
    cuenta = session.execute(
        select(Account).where(Account.alias == alias.strip().lower())
    ).scalar_one_or_none()
    if cuenta is None:
        raise NotFoundError("La cuenta de destino no existe.")
    return cuenta


def lock_pair(
    session: Session, first_id: uuid.UUID, second_id: uuid.UUID
) -> dict[uuid.UUID, Account]:
    """Bloquea dos cuentas en orden determinista. Ver ADR-0005.

    Se emiten DOS sentencias separadas en orden ascendente de identificador en
    lugar de un único `WHERE id IN (...) ORDER BY id FOR UPDATE`, porque el
    orden en que PostgreSQL adquiere los bloqueos de un conjunto depende del
    plan de ejecución y no está garantizado. Con sentencias separadas el orden
    es el que impone la aplicación, y como todas las instancias ordenan igual,
    la espera circular (deadlock) se vuelve imposible.
    """
    orden = sorted([first_id, second_id])
    bloqueadas: dict[uuid.UUID, Account] = {}
    for account_id in orden:
        cuenta = session.execute(
            select(Account).where(Account.id == account_id).with_for_update()
        ).scalar_one_or_none()
        if cuenta is None:
            raise NotFoundError("La cuenta no existe.")
        bloqueadas[account_id] = cuenta
    return bloqueadas


def get_system_funding_account(session: Session) -> Account:
    """Cuenta de sistema desde la que se acredita el saldo ficticio.

    Es la única exenta de la restricción de no negatividad, de modo que la suma
    global de asientos sigue siendo exactamente cero. Ver ADR-0004.
    """
    cuenta = session.execute(
        select(Account).where(Account.alias == SYSTEM_FUNDING_ALIAS)
    ).scalar_one_or_none()
    if cuenta is None:
        cuenta = Account(
            user_id=None,
            alias=SYSTEM_FUNDING_ALIAS,
            kind=ACCOUNT_KIND_SYSTEM,
            balance_cents=0,
        )
        session.add(cuenta)
        session.flush()
    return cuenta
