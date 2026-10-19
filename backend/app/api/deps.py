"""Dependencias compartidas de la API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.identity.security import decode_access_token
from app.platform.errors import AuthenticationError

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
