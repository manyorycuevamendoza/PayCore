"""Registro y autenticación."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import limitar_login
from app.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.identity import service as identity_service
from app.modules.identity.security import create_access_token
from app.platform.db import transactional, unit_of_work

router = APIRouter(prefix="/auth", tags=["autenticación"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un usuario ficticio",
    responses={
        409: {"description": "El correo ya está registrado"},
        422: {"description": "Datos inválidos o alias en uso"},
        429: {"description": "Demasiados intentos desde este origen"},
    },
    dependencies=[Depends(limitar_login)],
)
def register(peticion: RegisterRequest) -> UserResponse:
    def operacion(session):
        usuario, cuenta = identity_service.register(
            session,
            email=peticion.email,
            password=peticion.password,
            full_name=peticion.full_name,
            alias=peticion.alias,
        )
        return UserResponse(
            id=usuario.id,
            email=usuario.email,
            full_name=usuario.full_name,
            alias=cuenta.alias,
        )

    return transactional(operacion)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Obtener un token de acceso",
    responses={
        401: {"description": "Credenciales inválidas"},
        429: {"description": "Demasiados intentos desde este origen"},
    },
    dependencies=[Depends(limitar_login)],
)
def login(peticion: LoginRequest) -> TokenResponse:
    with unit_of_work() as session:
        usuario = identity_service.authenticate(
            session, email=peticion.email, password=peticion.password
        )
        token, expira_en = create_access_token(usuario.id)
    return TokenResponse(access_token=token, expires_in=expira_en)
