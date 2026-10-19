"""Caso de uso de transferencia. Ver ADR-0004 y ADR-0005.

Todo lo que hace este módulo ocurre dentro de la transacción que abre quien
llama. No confirma nada por su cuenta: el COMMIT lo decide la unidad de
trabajo, y ese COMMIT cubre a la vez los asientos, los saldos y el registro de
idempotencia.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts import service as accounts_service
from app.modules.accounts.models import Account
from app.modules.ledger import service as ledger_service
from app.modules.transfers.models import (
    REASON_INSUFFICIENT_FUNDS,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    Transfer,
)
from app.platform.errors import NotFoundError, SameAccountTransferError, ValidationError
from app.platform.money import MAX_TRANSFER_CENTS

# Se eliminan caracteres de control del concepto antes de persistirlo.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class TransferResult:
    transfer: Transfer
    source_alias: str
    destination_alias: str
    source_balance_after_cents: int

    @property
    def completed(self) -> bool:
        return self.transfer.status == STATUS_COMPLETED


def _sanitizar_concepto(concepto: str | None) -> str | None:
    if concepto is None:
        return None
    limpio = _CONTROL.sub("", concepto).strip()
    return limpio[:140] or None


def execute_transfer(
    session: Session,
    *,
    source_account_id: uuid.UUID,
    destination_alias: str,
    amount_cents: int,
    concept: str | None = None,
) -> TransferResult:
    """Mueve saldo entre dos cuentas, o deja constancia del rechazo.

    Devuelve el resultado en lugar de lanzar una excepción cuando el rechazo es
    de negocio (fondos insuficientes), porque ese rechazo DEBE persistirse: la
    transferencia rechazada queda en el historial y su respuesta se guarda en
    el registro de idempotencia. Lanzar aquí abortaría la transacción y
    perderíamos las dos cosas.
    """
    if amount_cents <= 0:
        raise ValidationError(
            "El importe debe ser un número entero de céntimos mayor que cero.",
            {"campo": "amount_cents"},
        )
    if amount_cents > MAX_TRANSFER_CENTS:
        raise ValidationError(
            "El importe supera el máximo permitido por operación.",
            {"campo": "amount_cents", "maximo_cents": MAX_TRANSFER_CENTS},
        )

    destino = accounts_service.get_by_alias(session, destination_alias)
    if destino.id == source_account_id:
        raise SameAccountTransferError()

    # Orden determinista de bloqueo: elimina la espera circular. Ver ADR-0005.
    bloqueadas = accounts_service.lock_pair(session, source_account_id, destino.id)
    origen = bloqueadas[source_account_id]
    destino = bloqueadas[destino.id]

    concepto = _sanitizar_concepto(concept)

    if origen.balance_cents < amount_cents:
        rechazada = Transfer(
            source_account_id=origen.id,
            destination_account_id=destino.id,
            amount_cents=amount_cents,
            status=STATUS_REJECTED,
            rejection_reason=REASON_INSUFFICIENT_FUNDS,
            concept=concepto,
        )
        session.add(rechazada)
        session.flush()
        return TransferResult(
            transfer=rechazada,
            source_alias=origen.alias,
            destination_alias=destino.alias,
            source_balance_after_cents=origen.balance_cents,
        )

    transferencia = Transfer(
        source_account_id=origen.id,
        destination_account_id=destino.id,
        amount_cents=amount_cents,
        status=STATUS_COMPLETED,
        concept=concepto,
        completed_at=datetime.now(UTC),
    )
    session.add(transferencia)
    session.flush()

    ledger_service.record_double_entry(
        session,
        transfer_id=transferencia.id,
        source=origen,
        destination=destino,
        amount_cents=amount_cents,
    )

    return TransferResult(
        transfer=transferencia,
        source_alias=origen.alias,
        destination_alias=destino.alias,
        source_balance_after_cents=origen.balance_cents,
    )


def fund_account(
    session: Session, *, destination: Account, amount_cents: int, concept: str = "Carga inicial"
) -> Transfer:
    """Operación ADMINISTRATIVA: acredita saldo ficticio desde SYSTEM_FUNDING.

    Es la única excepción declarada a la conservación del saldo total, y no es
    realmente una excepción: el dinero sale de una cuenta de sistema que sí
    puede quedar en negativo, por lo que la suma global de asientos sigue
    siendo exactamente cero y el origen queda auditado. Ver ADR-0004.

    No se expone por la API. Solo la usan el script de datos de prueba y los
    tests.
    """
    if amount_cents <= 0:
        raise ValueError("El importe de financiación debe ser positivo")

    sistema = accounts_service.get_system_funding_account(session)
    bloqueadas = accounts_service.lock_pair(session, sistema.id, destination.id)
    sistema = bloqueadas[sistema.id]
    destino = bloqueadas[destination.id]

    movimiento = Transfer(
        source_account_id=sistema.id,
        destination_account_id=destino.id,
        amount_cents=amount_cents,
        status=STATUS_COMPLETED,
        concept=concept,
        completed_at=datetime.now(UTC),
    )
    session.add(movimiento)
    session.flush()

    ledger_service.record_double_entry(
        session,
        transfer_id=movimiento.id,
        source=sistema,
        destination=destino,
        amount_cents=amount_cents,
    )
    return movimiento


def get_for_account(
    session: Session, *, transfer_id: uuid.UUID, account_id: uuid.UUID
) -> Transfer:
    """Recupera una transferencia solo si la cuenta participa en ella.

    Si no participa se devuelve 404 y no 403: un 403 confirmaría que la
    transferencia existe y permitiría enumerarlas. Mitigación de API1:2023.
    """
    transferencia = session.execute(
        select(Transfer).where(
            Transfer.id == transfer_id,
            (Transfer.source_account_id == account_id)
            | (Transfer.destination_account_id == account_id),
        )
    ).scalar_one_or_none()
    if transferencia is None:
        raise NotFoundError("La operación no existe.")
    return transferencia
