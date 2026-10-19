from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db import Base

ACCOUNT_KIND_USER = "user"
ACCOUNT_KIND_SYSTEM = "system"

# Alias de la cuenta de sistema desde la que se acredita el saldo ficticio inicial.
# Ver ADR-0004: es la única cuenta exenta de la restricción de no negatividad,
# de modo que la suma global de asientos sigue siendo exactamente cero.
SYSTEM_FUNDING_ALIAS = "SYSTEM_FUNDING"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        # I1: ningún saldo de usuario puede quedar negativo. La garantía vive en
        # el motor, no en Python. La cuenta de sistema está exenta a propósito.
        CheckConstraint(
            "kind = 'system' OR balance_cents >= 0", name="ck_accounts_balance_no_negativo"
        ),
        CheckConstraint("kind IN ('user', 'system')", name="ck_accounts_kind"),
        CheckConstraint("currency = 'PEN'", name="ck_accounts_currency_pen"),
        # Una cuenta de usuario siempre tiene dueño; una de sistema, nunca.
        CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL) "
            "OR (kind = 'system' AND user_id IS NULL)",
            name="ck_accounts_propiedad_coherente",
        ),
        CheckConstraint("char_length(alias) BETWEEN 3 AND 32", name="ck_accounts_alias_len"),
        # MVP: una cuenta por usuario. PostgreSQL admite múltiples NULL aquí,
        # por lo que las cuentas de sistema no chocan entre sí.
        UniqueConstraint("user_id", name="uq_accounts_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    alias: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'PEN'"))
    balance_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user = relationship("User", back_populates="account")
