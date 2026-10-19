from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"

REASON_INSUFFICIENT_FUNDS = "insufficient_funds"


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        # I2: importe estrictamente positivo.
        CheckConstraint("amount_cents > 0", name="ck_transfers_importe_positivo"),
        # I3: origen distinto de destino.
        CheckConstraint(
            "source_account_id <> destination_account_id",
            name="ck_transfers_origen_distinto_destino",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'rejected')", name="ck_transfers_status"
        ),
        # Una transferencia rechazada tiene motivo, y solo ella lo tiene.
        CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_transfers_motivo_coherente",
        ),
        # Una transferencia completada tiene fecha de completado, y solo ella.
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_transfers_completado_coherente",
        ),
        Index("ix_transfers_source_created", "source_account_id", "created_at"),
        Index("ix_transfers_destination_created", "destination_account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    destination_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    concept: Mapped[str | None] = mapped_column(String(140), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
