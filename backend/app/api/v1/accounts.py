"""Consulta de cuenta, saldo e historial.

Todas las rutas derivan la cuenta del token. En ningún punto se acepta un
identificador de cuenta del cliente: es la mitigación de API1:2023.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUserId
from app.api.schemas import (
    AccountResponse,
    BalanceResponse,
    MovementPage,
    MovementResponse,
)
from app.modules.accounts import service as accounts_service
from app.modules.identity import service as identity_service
from app.modules.ledger import service as ledger_service
from app.platform.db import get_db_session
from app.platform.errors import NotFoundError
from app.platform.money import cents_to_display

router = APIRouter(prefix="/accounts", tags=["cuentas"])


@router.get("/me", response_model=AccountResponse, summary="Cuenta propia")
def get_my_account(
    user_id: CurrentUserId, session: Session = Depends(get_db_session)
) -> AccountResponse:
    cuenta = accounts_service.get_by_user(session, user_id)
    usuario = identity_service.get_by_id(session, user_id)
    if usuario is None:
        raise NotFoundError("La cuenta no existe.")
    return AccountResponse(
        id=cuenta.id,
        alias=cuenta.alias,
        balance_cents=cuenta.balance_cents,
        balance_display=cents_to_display(cuenta.balance_cents),
        owner_full_name=usuario.full_name,
    )


@router.get(
    "/me/balance", response_model=BalanceResponse, summary="Saldo disponible simulado"
)
def get_my_balance(
    user_id: CurrentUserId, session: Session = Depends(get_db_session)
) -> BalanceResponse:
    cuenta = accounts_service.get_by_user(session, user_id)
    return BalanceResponse(
        account_id=cuenta.id,
        balance_cents=cuenta.balance_cents,
        balance_display=cents_to_display(cuenta.balance_cents),
        as_of=datetime.now(UTC),
    )


@router.get(
    "/me/transactions",
    response_model=MovementPage,
    summary="Historial de movimientos",
)
def list_my_transactions(
    user_id: CurrentUserId,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> MovementPage:
    cuenta = accounts_service.get_by_user(session, user_id)
    movimientos, total = ledger_service.list_movements(
        session, account_id=cuenta.id, limit=limit, offset=offset
    )
    return MovementPage(
        items=[
            MovementResponse(
                transfer_id=m.transfer_id,
                direction="in" if m.signed_amount_cents > 0 else "out",
                amount_cents=abs(m.signed_amount_cents),
                amount_display=cents_to_display(abs(m.signed_amount_cents)),
                signed_amount_cents=m.signed_amount_cents,
                balance_after_cents=m.balance_after_cents,
                counterparty_alias=m.counterparty_alias,
                concept=m.concept,
                created_at=m.created_at,
            )
            for m in movimientos
        ],
        limit=limit,
        offset=offset,
        total=total,
    )
