"""H3. Registro, autenticación y protección de los endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from tests.conftest import registrar

pytestmark = pytest.mark.integration


def test_registro_crea_usuario_y_cuenta_con_saldo_cero(
    cliente, engine: Engine
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")

    cuenta = cliente.get("/api/v1/accounts/me", headers=ana.auth).json()
    assert cuenta["alias"] == "ana"
    assert cuenta["balance_cents"] == 0
    assert cuenta["balance_display"] == "0.00"
    assert cuenta["currency"] == "PEN"


def test_la_contrasena_se_guarda_con_argon2id_y_nunca_en_claro(
    cliente, engine: Engine
) -> None:
    registrar(cliente, alias="ana", nombre="Ana Quispe", password="ContrasenaLarga123")

    with engine.connect() as conn:
        hash_guardado = conn.execute(
            text("SELECT password_hash FROM users WHERE email = 'ana@ejemplo.pe'")
        ).scalar_one()

    assert hash_guardado.startswith("$argon2id$")
    assert "ContrasenaLarga123" not in hash_guardado
    # Parámetros de OWASP: 19 MiB de memoria, 2 iteraciones, 1 de paralelismo.
    assert "m=19456,t=2,p=1" in hash_guardado


def test_no_se_puede_repetir_el_correo(cliente) -> None:
    registrar(cliente, alias="ana", nombre="Ana Quispe")
    repetido = cliente.post(
        "/api/v1/auth/register",
        json={
            "email": "ana@ejemplo.pe",
            "password": "OtraContrasena99",
            "full_name": "Otra Persona",
            "alias": "otra",
        },
    )
    assert repetido.status_code == 409
    assert repetido.json()["error"]["code"] == "email_already_registered"


def test_el_correo_no_distingue_mayusculas(cliente) -> None:
    registrar(cliente, alias="ana", nombre="Ana Quispe")
    repetido = cliente.post(
        "/api/v1/auth/register",
        json={
            "email": "ANA@Ejemplo.Pe",
            "password": "OtraContrasena99",
            "full_name": "Otra Persona",
            "alias": "otra",
        },
    )
    assert repetido.status_code == 409


def test_no_se_puede_repetir_el_alias(cliente) -> None:
    registrar(cliente, alias="ana", nombre="Ana Quispe")
    repetido = cliente.post(
        "/api/v1/auth/register",
        json={
            "email": "otra@ejemplo.pe",
            "password": "OtraContrasena99",
            "full_name": "Otra Persona",
            "alias": "ana",
        },
    )
    assert repetido.status_code == 422


def test_login_con_contrasena_incorrecta(cliente) -> None:
    registrar(cliente, alias="ana", nombre="Ana Quispe")
    fallo = cliente.post(
        "/api/v1/auth/login",
        json={"email": "ana@ejemplo.pe", "password": "EstaNoEsLaBuena"},
    )
    assert fallo.status_code == 401
    assert fallo.json()["error"]["code"] == "authentication_failed"


def test_login_con_correo_inexistente_da_el_mismo_error(cliente) -> None:
    """Distinguir los dos casos permitiría enumerar correos registrados."""
    registrar(cliente, alias="ana", nombre="Ana Quispe")
    inexistente = cliente.post(
        "/api/v1/auth/login",
        json={"email": "nadie@ejemplo.pe", "password": "ContrasenaLarga123"},
    )
    mala_contrasena = cliente.post(
        "/api/v1/auth/login",
        json={"email": "ana@ejemplo.pe", "password": "EstaNoEsLaBuena"},
    )
    assert inexistente.status_code == mala_contrasena.status_code == 401
    assert (
        inexistente.json()["error"]["code"] == mala_contrasena.json()["error"]["code"]
    )


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/v1/accounts/me",
        "/api/v1/accounts/me/balance",
        "/api/v1/accounts/me/transactions",
    ],
)
def test_sin_token_no_se_accede(cliente, ruta: str) -> None:
    assert cliente.get(ruta).status_code == 401


def test_token_con_firma_invalida(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    manipulado = ana.token[:-4] + ("aaaa" if not ana.token.endswith("aaaa") else "bbbb")
    respuesta = cliente.get(
        "/api/v1/accounts/me", headers={"Authorization": f"Bearer {manipulado}"}
    )
    assert respuesta.status_code == 401


def test_token_caducado(cliente, monkeypatch) -> None:
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.modules.identity import security

    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    pasado = datetime.now(UTC) - timedelta(hours=2)
    caducado = jwt.encode(
        {
            "sub": str(ana.user_id),
            "iat": int(pasado.timestamp()),
            "exp": int((pasado + timedelta(minutes=15)).timestamp()),
            "jti": _uuid.uuid4().hex,
        },
        security._secret(),
        algorithm="HS256",
    )
    respuesta = cliente.get(
        "/api/v1/accounts/me", headers={"Authorization": f"Bearer {caducado}"}
    )
    assert respuesta.status_code == 401
    assert "caducado" in respuesta.json()["error"]["message"].lower()


def test_el_registro_rechaza_contrasenas_cortas(cliente) -> None:
    respuesta = cliente.post(
        "/api/v1/auth/register",
        json={
            "email": "corta@ejemplo.pe",
            "password": "corta",
            "full_name": "Persona",
            "alias": "corta",
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "validation_error"
