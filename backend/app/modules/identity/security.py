"""Hashing de contraseñas y emisión de tokens. Ver ADR-0007.

Argon2id con la configuración mínima que recomienda la hoja de OWASP sobre
almacenamiento de contraseñas: 19 MiB de memoria, 2 iteraciones y 1 grado de
paralelismo. Los parámetros no son una elección arbitraria, son citables.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.platform.config import get_settings
from app.platform.errors import AuthenticationError

# OWASP Password Storage Cheat Sheet: m=19456 (19 MiB), t=2, p=1.
ARGON2_MEMORY_KIB = 19_456
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1

_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_KIB,
    parallelism=ARGON2_PARALLELISM,
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def needs_rehash(password_hash: str) -> bool:
    """True si el hash se creó con parámetros más débiles que los actuales."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """Devuelve el token y los segundos que le quedan de vida."""
    settings = get_settings()
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "iat": int(ahora.timestamp()),
        "exp": int(expira.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, _secret(), algorithm=settings.jwt_algorithm)
    return token, settings.access_token_minutes * 60


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("El token ha caducado.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("El token no es válido.") from exc

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("El token no es válido.") from exc


def _secret() -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        if settings.is_production:
            raise RuntimeError("PAYCORE_JWT_SECRET es obligatorio en producción")
        # Solo en desarrollo y pruebas: evita que el arranque falle por olvido.
        return "dev-secret-solo-para-desarrollo-no-usar-en-produccion"
    return settings.jwt_secret
