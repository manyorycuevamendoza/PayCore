"""Transferencias. Es el endpoint donde se juega todo el proyecto.

Un único COMMIT confirma a la vez los asientos del ledger, los saldos
materializados y el registro de idempotencia. Ver ADR-0004, ADR-0005 y
ADR-0006.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUserId
from app.api.errors import error_body
from app.api.schemas import TransferRequest, TransferResponse
from app.modules.accounts import service as accounts_service
from app.modules.idempotency import service as idempotency_service
from app.modules.idempotency.service import Outcome
from app.modules.transfers import service as transfers_service
from app.modules.transfers.models import REASON_INSUFFICIENT_FUNDS
from app.platform.db import get_db_session, transactional
from app.platform.errors import (
    IdempotencyKeyInProgressError,
    IdempotencyKeyRequiredError,
    IdempotencyKeyReusedError,
    InsufficientFundsError,
    ValidationError,
)
from app.platform.money import cents_to_display

router = APIRouter(tags=["transferencias"])

RUTA = "/api/v1/transfers"


def _cuerpo_exito(resultado: transfers_service.TransferResult) -> dict[str, Any]:
    transferencia = resultado.transfer
    respuesta = TransferResponse(
        id=transferencia.id,
        status=transferencia.status,
        amount_cents=transferencia.amount_cents,
        amount_display=cents_to_display(transferencia.amount_cents),
        source_alias=resultado.source_alias,
        destination_alias=resultado.destination_alias,
        concept=transferencia.concept,
        created_at=transferencia.created_at,
        completed_at=transferencia.completed_at,
        source_balance_after_cents=resultado.source_balance_after_cents,
    )
    return respuesta.model_dump(mode="json")


def _cuerpo_rechazo(resultado: transfers_service.TransferResult) -> dict[str, Any]:
    return error_body(
        InsufficientFundsError.code,
        InsufficientFundsError.message,
        {
            "transfer_id": str(resultado.transfer.id),
            "status": resultado.transfer.status,
            "rejection_reason": REASON_INSUFFICIENT_FUNDS,
            "balance_cents": resultado.source_balance_after_cents,
            "amount_cents": resultado.transfer.amount_cents,
        },
    )


@router.post(
    "/transfers",
    status_code=status.HTTP_201_CREATED,
    response_model=TransferResponse,
    summary="Transferir saldo simulado entre cuentas",
    responses={
        400: {"description": "Falta la cabecera Idempotency-Key"},
        401: {"description": "No autenticado"},
        404: {"description": "La cuenta de destino no existe"},
        409: {"description": "Ya hay una petición en curso con esa clave"},
        422: {
            "description": "Fondos insuficientes, datos inválidos, o la clave de "
            "idempotencia se reutilizó con un cuerpo distinto"
        },
    },
)
def create_transfer(
    peticion: TransferRequest,
    user_id: CurrentUserId,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="UUID v4 generado por el cliente. Obligatorio.",
    ),
) -> JSONResponse:
    if not idempotency_key:
        raise IdempotencyKeyRequiredError()
    longitud = len(idempotency_key)
    if not (
        idempotency_service.MIN_KEY_LENGTH
        <= longitud
        <= idempotency_service.MAX_KEY_LENGTH
    ):
        raise ValidationError(
            "La clave de idempotencia debe tener entre "
            f"{idempotency_service.MIN_KEY_LENGTH} y "
            f"{idempotency_service.MAX_KEY_LENGTH} caracteres.",
            {"cabecera": "Idempotency-Key"},
        )

    huella = idempotency_service.fingerprint(
        "POST", RUTA, peticion.model_dump(mode="json")
    )

    def operacion(session: Session) -> tuple[bool, int, dict[str, Any]]:
        reclamacion = idempotency_service.claim(
            session, user_id=user_id, key=idempotency_key, request_fingerprint=huella
        )

        if reclamacion.outcome is Outcome.MISMATCH:
            raise IdempotencyKeyReusedError()
        if reclamacion.outcome is Outcome.IN_PROGRESS:
            raise IdempotencyKeyInProgressError()
        if reclamacion.outcome is Outcome.REPLAY:
            registro = reclamacion.record
            assert registro is not None
            return True, registro.response_status or 200, dict(registro.response_body or {})

        registro = reclamacion.record
        assert registro is not None

        origen = accounts_service.get_by_user(session, user_id)
        resultado = transfers_service.execute_transfer(
            session,
            source_account_id=origen.id,
            destination_alias=peticion.destination_alias,
            amount_cents=peticion.amount_cents,
            concept=peticion.concept,
        )

        if resultado.completed:
            codigo = status.HTTP_201_CREATED
            cuerpo = _cuerpo_exito(resultado)
        else:
            codigo = status.HTTP_422_UNPROCESSABLE_CONTENT
            cuerpo = _cuerpo_rechazo(resultado)

        # La clave se cierra DENTRO de la misma transacción que movió el saldo.
        # Si el proceso muere ahora, el ROLLBACK deshace las dos cosas; si muere
        # tras el COMMIT, el reintento encuentra esta respuesta y la reproduce.
        idempotency_service.finish(
            session,
            registro,
            status_code=codigo,
            body=cuerpo,
            transfer_id=resultado.transfer.id,
            succeeded=resultado.completed,
        )
        return False, codigo, cuerpo

    es_replay, codigo, cuerpo = transactional(operacion)

    cabeceras = {"Idempotent-Replay": "true"} if es_replay else {}
    return JSONResponse(status_code=codigo, content=cuerpo, headers=cabeceras)


@router.get(
    "/transfers/{transfer_id}",
    response_model=TransferResponse,
    summary="Estado de una operación",
    responses={404: {"description": "La operación no existe o no participas en ella"}},
)
def get_transfer(
    transfer_id: uuid.UUID,
    user_id: CurrentUserId,
    session: Session = Depends(get_db_session),
) -> TransferResponse:
    cuenta = accounts_service.get_by_user(session, user_id)
    transferencia = transfers_service.get_for_account(
        session, transfer_id=transfer_id, account_id=cuenta.id
    )
    origen = session.get(type(cuenta), transferencia.source_account_id)
    destino = session.get(type(cuenta), transferencia.destination_account_id)
    return TransferResponse(
        id=transferencia.id,
        status=transferencia.status,
        amount_cents=transferencia.amount_cents,
        amount_display=cents_to_display(transferencia.amount_cents),
        source_alias=origen.alias if origen else "",
        destination_alias=destino.alias if destino else "",
        concept=transferencia.concept,
        created_at=transferencia.created_at,
        completed_at=transferencia.completed_at,
        rejection_reason=transferencia.rejection_reason,
    )
