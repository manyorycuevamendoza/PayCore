"""Dependencias compartidas de la API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.identity.security import decode_access_token
from app.platform.config import get_settings
from app.platform.errors import AuthenticationError, RateLimitExceededError
from app.platform.rate_limit import RateLimiter

# auto_error=False para que la ausencia de cabecera produzca nuestro formato de
# error uniforme y no el de Starlette.
_bearer = HTTPBearer(auto_error=False, description="Token JWT de acceso")


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    """Identidad del autor de la petición, tomada del token.

    No consulta la base de datos: el token es autocontenido y verificado por
    firma. La contrapartida, declarada en ADR-0007, es que no hay revocación
    inmediata; se mitiga con una vida de token corta.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Falta la cabecera Authorization.")
    return decode_access_token(credentials.credentials)


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


# --- Limitación de peticiones ----------------------------------------------
#
# Mitiga API4:2023 y, en la transferencia, API6:2023. El login se limita por
# dirección de origen y la transferencia por usuario autenticado, que es la
# clave correcta en cada caso: en el login todavía no sabemos quién es, y en
# la transferencia sí, y limitar por IP castigaría a toda una red compartida.
#
# No se confía en X-Forwarded-For: es trivial de falsificar salvo que haya un
# proxy de confianza que la reescriba, y PayCore no lo tiene. Si algún día se
# despliega detrás de uno, hay que tratarla explícitamente.

_login_limiter: RateLimiter | None = None
_transfer_limiter: RateLimiter | None = None


def _limiters() -> tuple[RateLimiter, RateLimiter]:
    global _login_limiter, _transfer_limiter
    if _login_limiter is None or _transfer_limiter is None:
        ajustes = get_settings()
        _login_limiter = RateLimiter(
            capacity=ajustes.login_rate_burst,
            refill_per_second=ajustes.login_rate_per_minute / 60.0,
        )
        _transfer_limiter = RateLimiter(
            capacity=ajustes.transfer_rate_burst,
            refill_per_second=ajustes.transfer_rate_per_minute / 60.0,
        )
    return _login_limiter, _transfer_limiter


def reset_rate_limiters() -> None:
    """Descarta el estado acumulado. Lo usan las pruebas."""
    global _login_limiter, _transfer_limiter
    _login_limiter = None
    _transfer_limiter = None


def _aplicar(limiter: RateLimiter, clave: str) -> None:
    permitido, espera = limiter.check(clave)
    if permitido:
        return
    segundos = max(1, int(espera + 0.999))
    raise RateLimitExceededError(headers={"Retry-After": str(segundos)})


def limitar_login(request: Request) -> None:
    if not get_settings().rate_limit_enabled:
        return
    login_limiter, _ = _limiters()
    origen = request.client.host if request.client else "desconocido"
    _aplicar(login_limiter, f"login:{origen}")


def limitar_transferencia(user_id: CurrentUserId) -> None:
    if not get_settings().rate_limit_enabled:
        return
    _, transfer_limiter = _limiters()
    _aplicar(transfer_limiter, f"transfer:{user_id}")
