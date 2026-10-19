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


def fetch_pair(
    session: Session,
    first_id: uuid.UUID,
    second_id: uuid.UUID,
    *,
    for_update: bool,
) -> dict[uuid.UUID, Account]:
    """Recupera dos cuentas, opcionalmente bloqueándolas. Ver ADR-0005.

    Con `for_update=True` (estrategia pesimista) se emiten DOS sentencias
    separadas en orden ascendente de identificador, en lugar de un único
    `WHERE id IN (...) ORDER BY id FOR UPDATE`. El motivo es que el orden en
    que PostgreSQL adquiere los bloqueos de un conjunto depende del plan de
    ejecución y no está garantizado, mientras que con sentencias separadas el
    orden lo impone la aplicación. Como todas las instancias ordenan igual, la
    espera circular (deadlock) se vuelve imposible.

    Con `for_update=False` (estrategia SERIALIZABLE) no se toma ningún bloqueo
    de fila: la detección de conflictos la hace el propio SSI de PostgreSQL y
    la aplicación reintenta ante SQLSTATE 40001. Tomar bloqueos aquí
    desvirtuaría el experimento de la Fase 7, porque las dos estrategias
    dejarían de ser distinguibles.
    """
    orden = sorted([first_id, second_id])
    cuentas: dict[uuid.UUID, Account] = {}
    for account_id in orden:
        consulta = select(Account).where(Account.id == account_id)
        if for_update:
            consulta = consulta.with_for_update()
        # populate_existing es imprescindible, no es un adorno.
        #
        # Si la cuenta ya estaba en el mapa de identidad de la sesión por una
        # lectura anterior SIN bloqueo, SQLAlchemy devolvería ese mismo objeto
        # con sus atributos antiguos: la sentencia FOR UPDATE se ejecutaría y
        # el bloqueo se tomaría, pero el saldo que leería la lógica de negocio
        # sería el obsoleto. Eso es exactamente un lost update, y bajo carga
        # permitía aprobar transferencias sin fondos. Lo detectó la Prueba D.
        cuenta = (
            session.execute(consulta.execution_options(populate_existing=True))
            .scalar_one_or_none()
        )
        if cuenta is None:
            raise NotFoundError("La cuenta no existe.")
        cuentas[account_id] = cuenta
    return cuentas


def lock_pair(
    session: Session, first_id: uuid.UUID, second_id: uuid.UUID
) -> dict[uuid.UUID, Account]:
    """Atajo para el caso pesimista."""
    return fetch_pair(session, first_id, second_id, for_update=True)


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
