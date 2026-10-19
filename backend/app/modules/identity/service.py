"""Casos de uso de identidad: registro y autenticación."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.accounts.models import ACCOUNT_KIND_USER, Account
from app.modules.identity.models import User
from app.modules.identity.security import hash_password, verify_password
from app.platform.errors import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    ValidationError,
)


def register(
    session: Session, *, email: str, password: str, full_name: str, alias: str
) -> tuple[User, Account]:
    """Crea el usuario y su cuenta en la misma transacción.

    La cuenta nace con saldo cero. El dinero ficticio solo entra por una
    operación administrativa explícita contra SYSTEM_FUNDING (ver ADR-0004),
    nunca apareciendo de la nada al registrarse.
    """
    usuario = User(
        email=email.strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
    )
    session.add(usuario)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyRegisteredError() from exc

    cuenta = Account(
        user_id=usuario.id,
        alias=alias.strip().lower(),
        kind=ACCOUNT_KIND_USER,
        balance_cents=0,
    )
    session.add(cuenta)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValidationError(
            "Ese alias ya está en uso.", {"campo": "alias"}
        ) from exc

    return usuario, cuenta


def authenticate(session: Session, *, email: str, password: str) -> User:
    """Verifica credenciales.

    El mismo error para correo inexistente y contraseña incorrecta: distinguirlos
    permitiría enumerar qué correos están registrados.
    """
    usuario = session.execute(
        select(User).where(User.email == email.strip())
    ).scalar_one_or_none()

    if usuario is None:
        # Se consume tiempo comparable al de una verificación real para no
        # filtrar por latencia si el correo existe o no.
        hash_password(password)
        raise AuthenticationError()

    if not verify_password(usuario.password_hash, password):
        raise AuthenticationError()

    return usuario


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)
