"""Escritura del libro mayor y reconciliación. Ver ADR-0004."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.modules.accounts.models import Account
from app.modules.ledger.models import LedgerEntry


def record_double_entry(
    session: Session,
    *,
    transfer_id: uuid.UUID,
    source: Account,
    destination: Account,
    amount_cents: int,
) -> tuple[LedgerEntry, LedgerEntry]:
    """Aplica el movimiento: dos asientos opuestos y los saldos materializados.

    Las cuentas deben venir ya bloqueadas por quien llama. El saldo materializado
    y los asientos se escriben en la misma transacción, por lo que no pueden
    divergir: o se confirman los dos o ninguno.
    """
    if amount_cents <= 0:
        raise ValueError("El importe debe ser estrictamente positivo")

    source.balance_cents -= amount_cents
    destination.balance_cents += amount_cents

    debito = LedgerEntry(
        transfer_id=transfer_id,
        account_id=source.id,
        amount_cents=-amount_cents,
        balance_after_cents=source.balance_cents,
    )
    credito = LedgerEntry(
        transfer_id=transfer_id,
        account_id=destination.id,
        amount_cents=amount_cents,
        balance_after_cents=destination.balance_cents,
    )
    session.add_all([debito, credito])
    session.flush()
    return debito, credito


@dataclass(frozen=True)
class Discrepancia:
    account_id: uuid.UUID
    alias: str
    balance_cents: int
    suma_asientos: int


@dataclass(frozen=True)
class Reconciliacion:
    suma_global: int
    discrepancias: tuple[Discrepancia, ...]

    @property
    def cuadra(self) -> bool:
        return self.suma_global == 0 and not self.discrepancias


def reconcile(session: Session) -> Reconciliacion:
    """Recalcula los saldos desde el ledger y los compara con la proyección.

    Es la comprobación independiente que exige ADR-0004: verifica el resultado
    en los datos, no en el código que los produjo.
    """
    suma_global = session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
    ).scalar_one()

    sumas = (
        select(
            LedgerEntry.account_id,
            func.sum(LedgerEntry.amount_cents).label("suma"),
        )
        .group_by(LedgerEntry.account_id)
        .subquery()
    )

    filas = session.execute(
        select(
            Account.id,
            Account.alias,
            Account.balance_cents,
            func.coalesce(sumas.c.suma, 0),
        ).outerjoin(sumas, sumas.c.account_id == Account.id)
    ).all()

    discrepancias = tuple(
        Discrepancia(
            account_id=account_id,
            alias=alias,
            balance_cents=balance_cents,
            suma_asientos=int(suma),
        )
        for account_id, alias, balance_cents, suma in filas
        if balance_cents != int(suma)
    )

    return Reconciliacion(suma_global=int(suma_global), discrepancias=discrepancias)


@dataclass(frozen=True)
class Movimiento:
    transfer_id: uuid.UUID
    signed_amount_cents: int
    balance_after_cents: int
    counterparty_alias: str
    concept: str | None
    created_at: object


def list_movements(
    session: Session, *, account_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Movimiento], int]:
    """Historial de una cuenta, construido desde el ledger.

    El historial sale de los asientos y no de la tabla de transferencias,
    porque el ledger es la fuente de verdad: lo que se muestra es exactamente
    lo que movió el saldo.
    """
    from app.modules.transfers.models import Transfer

    contraparte = aliased(Account)

    total = session.execute(
        select(func.count())
        .select_from(LedgerEntry)
        .where(LedgerEntry.account_id == account_id)
    ).scalar_one()

    filas = session.execute(
        select(
            LedgerEntry.transfer_id,
            LedgerEntry.amount_cents,
            LedgerEntry.balance_after_cents,
            LedgerEntry.created_at,
            contraparte.alias,
            Transfer.concept,
        )
        .join(Transfer, Transfer.id == LedgerEntry.transfer_id)
        .join(
            contraparte,
            contraparte.id
            == case(
                (
                    Transfer.source_account_id == account_id,
                    Transfer.destination_account_id,
                ),
                else_=Transfer.source_account_id,
            ),
        )
        .where(LedgerEntry.account_id == account_id)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    movimientos = [
        Movimiento(
            transfer_id=transfer_id,
            signed_amount_cents=int(amount_cents),
            balance_after_cents=int(balance_after_cents),
            counterparty_alias=alias,
            concept=concepto,
            created_at=created_at,
        )
        for transfer_id, amount_cents, balance_after_cents, created_at, alias, concepto in filas
    ]
    return movimientos, int(total)
