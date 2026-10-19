"""Prueba F. Un usuario no puede operar ni consultar cuentas ajenas.

Ordenada por los riesgos del OWASP API Security Top 10 2023 que mitiga.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from tests.conftest import financiar, registrar, saldo_en_bd

pytestmark = [pytest.mark.integration, pytest.mark.security]


def _clave() -> str:
    return str(uuid.uuid4())


# --- API1:2023. Broken Object Level Authorization --------------------------


def test_no_se_puede_indicar_la_cuenta_de_origen_en_la_peticion(
    cliente, engine: Engine
) -> None:
    """La cuenta de origen se deriva del token y jamás del cuerpo.

    Si alguien añadiera un campo source_account_id, el esquema lo rechaza en
    vez de ignorarlo en silencio: ignorarlo dejaría al atacante creyendo que
    funcionó y a nosotros sin señal.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)
    financiar(luis, 100_00)

    with engine.connect() as conn:
        cuenta_de_luis = conn.execute(
            text("SELECT id FROM accounts WHERE alias = 'luis'")
        ).scalar_one()

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={
            "destination_alias": "ana",
            "amount_cents": 50_00,
            "source_account_id": str(cuenta_de_luis),
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "validation_error"
    # El saldo de Luis sigue intacto.
    assert saldo_en_bd(engine, "luis") == 100_00


def test_no_se_puede_consultar_una_operacion_ajena(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    intrusa = registrar(cliente, alias="rosa", nombre="Rosa Mamani")
    financiar(ana, 100_00)

    entre_ana_y_luis = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    ).json()

    ajena = cliente.get(
        f"/api/v1/transfers/{entre_ana_y_luis['id']}", headers=intrusa.auth
    )
    # 404 y no 403: un 403 confirmaría que la operación existe.
    assert ajena.status_code == 404
    assert ajena.json()["error"]["code"] == "not_found"

    # Quienes sí participan la ven.
    for quien in (ana, luis):
        assert (
            cliente.get(
                f"/api/v1/transfers/{entre_ana_y_luis['id']}", headers=quien.auth
            ).status_code
            == 200
        )


def test_el_historial_solo_muestra_movimientos_propios(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    rosa = registrar(cliente, alias="rosa", nombre="Rosa Mamani")
    financiar(ana, 100_00)

    cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )

    historial = cliente.get(
        "/api/v1/accounts/me/transactions", headers=rosa.auth
    ).json()
    assert historial["total"] == 0
    assert historial["items"] == []


# --- API3:2023. Broken Object Property Level Authorization -----------------


def test_el_registro_ignora_campos_que_no_le_corresponden(cliente, engine: Engine) -> None:
    respuesta = cliente.post(
        "/api/v1/auth/register",
        json={
            "email": "lista@ejemplo.pe",
            "password": "ContrasenaLarga123",
            "full_name": "Persona Lista",
            "alias": "lista",
            "balance_cents": 999_999_00,
        },
    )
    assert respuesta.status_code == 422


def test_ninguna_respuesta_expone_el_hash_de_la_contrasena(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    for ruta in ("/api/v1/accounts/me", "/api/v1/accounts/me/balance"):
        texto = cliente.get(ruta, headers=ana.auth).text
        assert "password" not in texto.lower()
        assert "argon2" not in texto.lower()


# --- Validación de importes ------------------------------------------------


@pytest.mark.parametrize(
    "importe",
    [0, -1, -100_00, 1_000_000_01, "treinta", 30.5, None, 10**20],
)
def test_importes_invalidos_se_rechazan(cliente, engine: Engine, importe) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": importe},
    )
    assert respuesta.status_code == 422, f"importe {importe!r} no fue rechazado"
    assert saldo_en_bd(engine, "ana") == 100_00
    assert saldo_en_bd(engine, "luis") == 0


def test_un_importe_decimal_no_se_redondea_en_el_servidor(
    cliente, engine: Engine
) -> None:
    """amount_cents es un entero de céntimos. Si llega un decimal, se rechaza:
    redondearlo en silencio sería decidir por el usuario sobre su dinero."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 1000.4},
    )
    assert respuesta.status_code == 422
    assert saldo_en_bd(engine, "ana") == 100_00


# --- Inyección -------------------------------------------------------------


@pytest.mark.parametrize(
    "alias_malicioso",
    [
        "luis'; DROP TABLE accounts; --",
        "' OR '1'='1",
        "luis union select * from users",
    ],
)
def test_intentos_de_inyeccion_sql_en_el_alias(
    cliente, engine: Engine, alias_malicioso: str
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": alias_malicioso, "amount_cents": 10_00},
    )
    assert respuesta.status_code in (404, 422)

    # Las tablas siguen ahí: el ORM usa parámetros vinculados.
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar_one() >= 1


# --- API8:2023. Security Misconfiguration ----------------------------------


def test_ninguna_respuesta_de_error_expone_traza_interna(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    financiar(ana, 100_00)

    respuestas = [
        cliente.get("/api/v1/accounts/me"),
        cliente.get("/api/v1/transfers/no-es-un-uuid", headers=ana.auth),
        cliente.get(f"/api/v1/transfers/{uuid.uuid4()}", headers=ana.auth),
        cliente.post(
            "/api/v1/transfers",
            headers={**ana.auth, "Idempotency-Key": _clave()},
            json={"destination_alias": "nadie", "amount_cents": 10_00},
        ),
    ]
    for respuesta in respuestas:
        assert respuesta.status_code >= 400
        cuerpo = respuesta.text
        assert "Traceback" not in cuerpo
        assert "sqlalchemy" not in cuerpo.lower()
        assert "psycopg" not in cuerpo.lower()
        assert "/srv/" not in cuerpo
        error = respuesta.json()["error"]
        assert {"code", "message", "request_id", "details"} <= set(error)


def test_el_logging_redacta_los_campos_sensibles() -> None:
    from app.platform.logging import redact

    redactado = redact(
        {
            "password": "ContrasenaLarga123",
            "authorization": "Bearer abc.def.ghi",
            "idempotency_key": "clave-secreta",
            "amount_cents": 3000,
        }
    )
    assert redactado["password"] == "[REDACTADO]"
    assert redactado["authorization"] == "[REDACTADO]"
    assert redactado["idempotency_key"] == "[REDACTADO]"
    # Los importes sí se registran: son datos ficticios y hacen falta para auditar.
    assert redactado["amount_cents"] == 3000
