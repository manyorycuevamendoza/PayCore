from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

STATE_IN_PROGRESS = "in_progress"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"


class IdempotencyKey(Base):
    """Registro de idempotencia. Ver ADR-0006.

    Se escribe en la MISMA transacción que el movimiento de dinero, de modo
    que no existe ventana entre mover el saldo y dejar constancia de la clave.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # Ámbito por usuario: impide colisiones entre clientes y que alguien
        # recupere la respuesta almacenada de otro reutilizando su clave.
        UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
        CheckConstraint(
            "state IN ('in_progress', 'succeeded', 'failed')", name="ck_idempotency_state"
        ),
        CheckConstraint("char_length(key) BETWEEN 8 AND 255", name="ck_idempotency_key_len"),
        # Una clave finalizada siempre guarda la respuesta que debe reproducir.
        CheckConstraint(
            "(state = 'in_progress') OR (response_status IS NOT NULL)",
            name="ck_idempotency_respuesta_coherente",
        ),
        Index("ix_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transfers.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
