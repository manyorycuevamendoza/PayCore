from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base


class LedgerEntry(Base):
    """Asiento del libro mayor. Append-only: ver ADR-0004 e invariante I10.

    El signo codifica la dirección: negativo es débito, positivo es crédito.
    Cada transferencia completada produce exactamente dos asientos que suman
    cero, lo que verifica un trigger diferido al COMMIT (invariante I4).
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_cents <> 0", name="ck_ledger_importe_no_nulo"),
        # Una transferencia no puede tocar dos veces la misma cuenta.
        UniqueConstraint("transfer_id", "account_id", name="uq_ledger_transfer_account"),
        Index("ix_ledger_account_created", "account_id", "created_at"),
        Index("ix_ledger_transfer", "transfer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transfers.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
