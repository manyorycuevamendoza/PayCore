from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(full_name) BETWEEN 1 AND 120", name="ck_users_full_name_len"),
        CheckConstraint("char_length(email::text) BETWEEN 3 AND 254", name="ck_users_email_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # CITEXT hace la comparación de correos insensible a mayúsculas en el motor,
    # de modo que la unicidad no depende de que la aplicación normalice.
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account = relationship("Account", back_populates="user", uselist=False)
