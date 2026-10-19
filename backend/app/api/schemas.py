"""Esquemas de entrada y salida de la API.

Los importes viajan como entero de céntimos (`amount_cents`) y, para la
interfaz, también como cadena decimal ya formateada (`amount_display`).
Nunca como número en punto flotante. Ver ADR-0003.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.platform.money import CURRENCY, MAX_TRANSFER_CENTS

ALIAS_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,31}$"


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    alias: str = Field(min_length=3, max_length=32)

    @field_validator("alias")
    @classmethod
    def _alias_normalizado(cls, value: str) -> str:
        import re

        normalizado = value.strip().lower()
        if not re.fullmatch(ALIAS_PATTERN, normalizado):
            raise ValueError(
                "El alias solo admite minúsculas, dígitos, punto, guion y guion bajo, "
                "y debe empezar por letra o dígito."
            )
        return normalizado


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    alias: str


class AccountResponse(BaseModel):
    id: uuid.UUID
    alias: str
    currency: str = CURRENCY
    balance_cents: int
    balance_display: str
    owner_full_name: str


class BalanceResponse(BaseModel):
    account_id: uuid.UUID
    currency: str = CURRENCY
    balance_cents: int
    balance_display: str
    as_of: datetime


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_alias: str = Field(min_length=3, max_length=32)
    amount_cents: int = Field(gt=0, le=MAX_TRANSFER_CENTS)
    concept: str | None = Field(default=None, max_length=140)

    @field_validator("destination_alias")
    @classmethod
    def _normalizar(cls, value: str) -> str:
        return value.strip().lower()


class TransferResponse(BaseModel):
    id: uuid.UUID
    status: str
    amount_cents: int
    amount_display: str
    currency: str = CURRENCY
    source_alias: str
    destination_alias: str
    concept: str | None
    created_at: datetime
    completed_at: datetime | None
    source_balance_after_cents: int | None = None
    rejection_reason: str | None = None


class MovementResponse(BaseModel):
    transfer_id: uuid.UUID
    direction: str  # "in" | "out"
    amount_cents: int
    amount_display: str
    signed_amount_cents: int
    balance_after_cents: int
    counterparty_alias: str
    concept: str | None
    created_at: datetime


class MovementPage(BaseModel):
    items: list[MovementResponse]
    limit: int
    offset: int
    total: int
