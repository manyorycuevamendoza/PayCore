"""Idempotencia persistente. Ver ADR-0006.

La clave se reclama y se cierra dentro de la MISMA transacción que mueve el
dinero. Un único COMMIT cubre las dos cosas, por lo que no existe ningún
instante en el que el saldo haya cambiado y la clave no esté registrada.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.idempotency.models import (
    STATE_FAILED,
    STATE_IN_PROGRESS,
    STATE_SUCCEEDED,
    IdempotencyKey,
)
from app.platform.config import get_settings

MIN_KEY_LENGTH = 8
MAX_KEY_LENGTH = 255


def fingerprint(method: str, path: str, body: dict[str, Any]) -> str:
    """Huella estable del contenido de la petición.

    `sort_keys` hace que el orden de los campos del JSON no cambie la huella,
    de modo que un reintento byte a byte distinto pero semánticamente igual se
    reconoce como el mismo.
    """
    canonico = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    material = f"{method.upper()} {path} {canonico}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Outcome(Enum):
    CLAIMED = auto()      # esta petición es la primera, debe procesarse
    REPLAY = auto()       # ya hubo una respuesta, se reproduce tal cual
    IN_PROGRESS = auto()  # otra petición con la misma clave está en curso
    MISMATCH = auto()     # misma clave, cuerpo distinto


@dataclass(frozen=True)
class ClaimResult:
    outcome: Outcome
    record: IdempotencyKey | None = None


def claim(
    session: Session, *, user_id: uuid.UUID, key: str, request_fingerprint: str
) -> ClaimResult:
    """Intenta reclamar la clave de forma atómica.

    `INSERT ... ON CONFLICT DO NOTHING` es la reclamación: o esta transacción
    inserta la fila, y entonces le toca procesar, o no la inserta, y entonces
    debe mirar qué pasó con la petición original.
    """
    settings = get_settings()
    expira = datetime.now(UTC) + timedelta(hours=settings.idempotency_ttl_hours)

    sentencia = (
        pg_insert(IdempotencyKey)
        .values(
            user_id=user_id,
            key=key,
            request_fingerprint=request_fingerprint,
            state=STATE_IN_PROGRESS,
            expires_at=expira,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_user_key")
        .returning(IdempotencyKey.id)
    )
    insertada = session.execute(sentencia).scalar_one_or_none()

    if insertada is not None:
        registro = session.get(IdempotencyKey, insertada)
        return ClaimResult(Outcome.CLAIMED, registro)

    existente = session.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
        )
    ).scalar_one_or_none()

    if existente is None:
        # El INSERT chocó con una fila que otra transacción aún no ha
        # confirmado, por lo que en READ COMMITTED no la vemos. Semánticamente
        # es justo el caso de petición concurrente en curso.
        return ClaimResult(Outcome.IN_PROGRESS)

    if existente.request_fingerprint != request_fingerprint:
        return ClaimResult(Outcome.MISMATCH, existente)

    if existente.state == STATE_IN_PROGRESS:
        return ClaimResult(Outcome.IN_PROGRESS, existente)

    return ClaimResult(Outcome.REPLAY, existente)


def finish(
    session: Session,
    record: IdempotencyKey,
    *,
    status_code: int,
    body: dict[str, Any],
    transfer_id: uuid.UUID | None = None,
    succeeded: bool = True,
) -> None:
    """Cierra la clave guardando la respuesta que habrá que reproducir."""
    record.state = STATE_SUCCEEDED if succeeded else STATE_FAILED
    record.response_status = status_code
    record.response_body = body
    record.transfer_id = transfer_id
    session.flush()


def purge_expired(session: Session) -> int:
    """Elimina las claves caducadas. TTL de 24 h por defecto.

    Lo ejecuta scripts/purge-idempotency.sh. No es un trabajo en segundo plano
    porque añadir un planificador al MVP no está justificado.
    """
    resultado = session.execute(
        delete(IdempotencyKey).where(IdempotencyKey.expires_at < datetime.now(UTC))
    )
    return resultado.rowcount or 0
