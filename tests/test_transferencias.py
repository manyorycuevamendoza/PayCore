"""H4 y H5. Pruebas A y B del enunciado, verificadas en la base de datos.

Comprobar el código HTTP no demuestra nada sobre el dinero. Cada aserción
relevante consulta PostgreSQL directamente.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from tests.conftest import (
    asientos_de,
    comprobar_reconciliacion,
    financiar,
    registrar,
    saldo_en_bd,
)

pytestmark = pytest.mark.integration


def _clave() -> str:
    return str(uuid.uuid4())


# --- Prueba A. Transferencia correcta --------------------------------------


def test_prueba_a_transferencia_correcta(cliente, engine: Engine) -> None:
    """Ana tiene S/100 y Luis S/20. Ana envía S/30.

    Resultado esperado: Ana S/70 y Luis S/50.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)
    financiar(luis, 20_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00, "concept": "Almuerzo"},
    )
    assert respuesta.status_code == 201, respuesta.text

    cuerpo = respuesta.json()
    assert cuerpo["status"] == "completed"
    assert cuerpo["amount_cents"] == 3000
    assert cuerpo["amount_display"] == "30.00"
    assert cuerpo["source_alias"] == "ana"
    assert cuerpo["destination_alias"] == "luis"

    # La verificación que importa: el estado real de la base de datos.
    assert saldo_en_bd(engine, "ana") == 70_00
    assert saldo_en_bd(engine, "luis") == 50_00

    # Dos asientos opuestos de la misma magnitud, ligados por la transferencia.
    assert asientos_de(engine, cuerpo["id"]) == [("ana", -3000), ("luis", 3000)]

    comprobar_reconciliacion(engine)


def test_el_saldo_consultado_coincide_con_el_de_la_base(
    cliente, engine: Engine
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )

    saldo = cliente.get("/api/v1/accounts/me/balance", headers=ana.auth).json()
    assert saldo["balance_cents"] == 70_00 == saldo_en_bd(engine, "ana")
    assert saldo["balance_display"] == "70.00"


# --- Prueba B. Fondos insuficientes ----------------------------------------


def test_prueba_b_fondos_insuficientes(cliente, engine: Engine) -> None:
    """Ana intenta enviar S/200 teniendo S/100.

    Resultado esperado: transferencia rechazada y saldos sin cambios.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)
    financiar(luis, 20_00)

    antes_ana = saldo_en_bd(engine, "ana")
    antes_luis = saldo_en_bd(engine, "luis")

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 200_00},
    )
    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["code"] == "insufficient_funds"
    assert error["details"]["rejection_reason"] == "insufficient_funds"

    # Los saldos no se han movido ni un céntimo.
    assert saldo_en_bd(engine, "ana") == antes_ana == 100_00
    assert saldo_en_bd(engine, "luis") == antes_luis == 20_00

    # El rechazo queda registrado, pero sin generar ningún asiento.
    transfer_id = error["details"]["transfer_id"]
    with engine.connect() as conn:
        estado = conn.execute(
            text("SELECT status FROM transfers WHERE id = :t"), {"t": transfer_id}
        ).scalar_one()
        asientos = conn.execute(
            text("SELECT count(*) FROM ledger_entries WHERE transfer_id = :t"),
            {"t": transfer_id},
        ).scalar_one()
    assert estado == "rejected"
    assert asientos == 0

    comprobar_reconciliacion(engine)


def test_no_se_puede_transferir_a_uno_mismo(cliente, engine: Engine) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "ana", "amount_cents": 10_00},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "same_account_transfer"
    assert saldo_en_bd(engine, "ana") == 100_00


def test_destino_inexistente(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "nadie", "amount_cents": 10_00},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "not_found"


def test_la_transferencia_exige_clave_de_idempotencia(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers=ana.auth,
        json={"destination_alias": "luis", "amount_cents": 10_00},
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["code"] == "idempotency_key_required"


# --- Historial y estado de operación ---------------------------------------


def test_el_historial_muestra_entradas_y_salidas(cliente, engine: Engine) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00, "concept": "Almuerzo"},
    )

    historial_ana = cliente.get(
        "/api/v1/accounts/me/transactions", headers=ana.auth
    ).json()
    # La carga inicial también es un movimiento auditado.
    assert historial_ana["total"] == 2
    salida = historial_ana["items"][0]
    assert salida["direction"] == "out"
    assert salida["amount_cents"] == 3000
    assert salida["signed_amount_cents"] == -3000
    assert salida["counterparty_alias"] == "luis"
    assert salida["balance_after_cents"] == 70_00
    assert salida["concept"] == "Almuerzo"

    historial_luis = cliente.get(
        "/api/v1/accounts/me/transactions", headers=luis.auth
    ).json()
    assert historial_luis["total"] == 1
    entrada = historial_luis["items"][0]
    assert entrada["direction"] == "in"
    assert entrada["counterparty_alias"] == "ana"


def test_consulta_del_estado_de_una_operacion(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    creada = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    ).json()

    for quien in (ana, luis):
        consulta = cliente.get(f"/api/v1/transfers/{creada['id']}", headers=quien.auth)
        assert consulta.status_code == 200
        assert consulta.json()["status"] == "completed"
        assert consulta.json()["amount_cents"] == 3000


def test_el_concepto_se_limpia_de_caracteres_de_control(
    cliente, engine: Engine
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    creada = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={
            "destination_alias": "luis",
            "amount_cents": 10_00,
            "concept": "Pago\x00con\x1bbasura",
        },
    ).json()
    assert creada["concept"] == "Pagoconbasura"


# --- La conservación del saldo total ---------------------------------------


def test_el_total_en_circulacion_no_cambia_con_las_transferencias(
    cliente, engine: Engine
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    rosa = registrar(cliente, alias="rosa", nombre="Rosa Mamani")
    financiar(ana, 100_00)
    financiar(luis, 50_00)

    def total_en_circulacion() -> int:
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT coalesce(sum(balance_cents), 0) FROM accounts "
                    "WHERE kind = 'user'"
                )
            ).scalar_one()

    antes = total_en_circulacion()

    for origen, destino, importe in (
        (ana, "luis", 30_00),
        (luis, "rosa", 15_00),
        (rosa, "ana", 5_00),
    ):
        respuesta = cliente.post(
            "/api/v1/transfers",
            headers={**origen.auth, "Idempotency-Key": _clave()},
            json={"destination_alias": destino, "amount_cents": importe},
        )
        assert respuesta.status_code == 201, respuesta.text

    assert total_en_circulacion() == antes == 150_00
    comprobar_reconciliacion(engine)
