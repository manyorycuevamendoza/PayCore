"""H6. Prueba C del enunciado y el resto del protocolo de idempotencia.

Ver ADR-0006. Lo que se verifica es que un reintento no crea movimientos
adicionales, comprobándolo en el ledger y no en la respuesta HTTP.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import Engine, text

from tests.conftest import comprobar_reconciliacion, financiar, registrar, saldo_en_bd

pytestmark = pytest.mark.integration


def _asientos_totales(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM ledger_entries")).scalar_one()


# --- Prueba C. Solicitud duplicada -----------------------------------------


def test_prueba_c_el_reintento_con_la_misma_clave_no_duplica(
    cliente, engine: Engine
) -> None:
    """Enviar dos veces la misma operación con la misma clave de idempotencia.

    Resultado esperado: una sola transferencia efectiva.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    clave = str(uuid.uuid4())
    cuerpo = {"destination_alias": "luis", "amount_cents": 30_00, "concept": "Almuerzo"}
    asientos_antes = _asientos_totales(engine)

    primera = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json=cuerpo,
    )
    segunda = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json=cuerpo,
    )

    assert primera.status_code == 201
    assert segunda.status_code == 201

    # La respuesta reproducida es idéntica y se marca como tal.
    assert segunda.json() == primera.json()
    assert segunda.headers.get("Idempotent-Replay") == "true"
    assert primera.headers.get("Idempotent-Replay") is None

    # Una sola transferencia efectiva: el saldo se movió una vez.
    assert saldo_en_bd(engine, "ana") == 70_00
    assert saldo_en_bd(engine, "luis") == 30_00

    # Y en el ledger solo hay un par de asientos nuevos.
    assert _asientos_totales(engine) == asientos_antes + 2

    with engine.connect() as conn:
        transferencias = conn.execute(
            text("SELECT count(*) FROM transfers WHERE concept = 'Almuerzo'")
        ).scalar_one()
    assert transferencias == 1

    comprobar_reconciliacion(engine)


def test_el_rechazo_por_fondos_tambien_es_idempotente(
    cliente, engine: Engine
) -> None:
    """Un 422 de negocio también se guarda y se reproduce igual."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 10_00)

    clave = str(uuid.uuid4())
    cuerpo = {"destination_alias": "luis", "amount_cents": 500_00}

    primera = cliente.post(
        "/api/v1/transfers", headers={**ana.auth, "Idempotency-Key": clave}, json=cuerpo
    )
    segunda = cliente.post(
        "/api/v1/transfers", headers={**ana.auth, "Idempotency-Key": clave}, json=cuerpo
    )

    assert primera.status_code == segunda.status_code == 422
    assert (
        segunda.json()["error"]["details"]["transfer_id"]
        == primera.json()["error"]["details"]["transfer_id"]
    )
    assert segunda.headers.get("Idempotent-Replay") == "true"

    with engine.connect() as conn:
        rechazos = conn.execute(
            text("SELECT count(*) FROM transfers WHERE status = 'rejected'")
        ).scalar_one()
    assert rechazos == 1


def test_misma_clave_con_cuerpo_distinto_devuelve_422(
    cliente, engine: Engine
) -> None:
    """Comportamiento recomendado por draft-ietf-httpapi-idempotency-key-header-07."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    clave = str(uuid.uuid4())
    cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )
    distinta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 50_00},
    )

    assert distinta.status_code == 422
    assert distinta.json()["error"]["code"] == "idempotency_key_reused"
    # El segundo importe no se movió.
    assert saldo_en_bd(engine, "ana") == 70_00


def test_el_orden_de_los_campos_no_cambia_la_huella(cliente, engine: Engine) -> None:
    """Un reintento con el JSON en otro orden sigue siendo el mismo."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    clave = str(uuid.uuid4())
    cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 30_00, "concept": "Cena"},
    )
    reintento = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"concept": "Cena", "amount_cents": 30_00, "destination_alias": "luis"},
    )
    assert reintento.status_code == 201
    assert reintento.headers.get("Idempotent-Replay") == "true"
    assert saldo_en_bd(engine, "ana") == 70_00


def test_una_peticion_en_curso_con_la_misma_clave_devuelve_409(
    cliente, engine: Engine
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    from app.modules.idempotency.service import fingerprint

    clave = str(uuid.uuid4())
    cuerpo = {"destination_alias": "luis", "amount_cents": 30_00, "concept": None}
    huella = fingerprint("POST", "/api/v1/transfers", cuerpo)

    # Simula que otra petición ya reclamó la clave y sigue procesando.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_keys "
                "(user_id, key, request_fingerprint, state, expires_at) "
                "VALUES (:u, :k, :f, 'in_progress', now() + interval '24 hours')"
            ),
            {"u": ana.user_id, "k": clave, "f": huella},
        )

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json=cuerpo,
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "idempotency_key_in_progress"
    assert saldo_en_bd(engine, "ana") == 100_00


def test_la_clave_es_privada_de_cada_usuario(cliente, engine: Engine) -> None:
    """Reutilizar la clave de otro no da acceso a su respuesta almacenada."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    registrar(cliente, alias="rosa", nombre="Rosa Mamani")
    financiar(ana, 100_00)
    financiar(luis, 100_00)

    clave = str(uuid.uuid4())
    de_ana = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "rosa", "amount_cents": 30_00},
    )
    assert de_ana.status_code == 201

    # Luis usa la MISMA clave: para él es nueva y su transferencia se ejecuta.
    de_luis = cliente.post(
        "/api/v1/transfers",
        headers={**luis.auth, "Idempotency-Key": clave},
        json={"destination_alias": "rosa", "amount_cents": 40_00},
    )
    assert de_luis.status_code == 201
    assert de_luis.json()["id"] != de_ana.json()["id"]
    assert de_luis.headers.get("Idempotent-Replay") is None

    assert saldo_en_bd(engine, "rosa") == 70_00
    comprobar_reconciliacion(engine)


@pytest.mark.parametrize("clave", ["", "corta", "x" * 256])
def test_claves_de_longitud_invalida(cliente, clave: str) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 10_00},
    )
    assert respuesta.status_code in (400, 422)


# --- Reentrada concurrente con la misma clave ------------------------------


@pytest.mark.concurrency
def test_dos_peticiones_simultaneas_con_la_misma_clave_solo_mueven_dinero_una_vez(
    cliente, engine: Engine
) -> None:
    """La reclamación con ON CONFLICT DO NOTHING es atómica.

    Se ataca el servicio directamente con dos hilos y dos conexiones reales,
    porque lo que se verifica es la atomicidad en PostgreSQL, no el cliente
    HTTP.
    """
    from app.modules.accounts import service as accounts_service
    from app.modules.idempotency import service as idempotency_service
    from app.modules.idempotency.service import Outcome
    from app.modules.transfers import service as transfers_service
    from app.platform.db import unit_of_work

    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    clave = str(uuid.uuid4())
    huella = "huella-identica-para-las-dos-peticiones"
    barrera = threading.Barrier(2)
    resultados: list[str] = []
    cerrojo = threading.Lock()

    def intentar() -> None:
        barrera.wait(timeout=10)
        try:
            with unit_of_work() as session:
                reclamacion = idempotency_service.claim(
                    session, user_id=ana.user_id, key=clave, request_fingerprint=huella
                )
                if reclamacion.outcome is not Outcome.CLAIMED:
                    with cerrojo:
                        resultados.append(reclamacion.outcome.name)
                    return
                origen = accounts_service.get_by_user(session, ana.user_id)
                resultado = transfers_service.execute_transfer(
                    session,
                    source_account_id=origen.id,
                    destination_alias="luis",
                    amount_cents=30_00,
                )
                idempotency_service.finish(
                    session,
                    reclamacion.record,
                    status_code=201,
                    body={"id": str(resultado.transfer.id)},
                    transfer_id=resultado.transfer.id,
                )
            with cerrojo:
                resultados.append("CLAIMED")
        except Exception as error:  # noqa: BLE001
            with cerrojo:
                resultados.append(f"ERROR:{type(error).__name__}")

    hilos = [threading.Thread(target=intentar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert resultados.count("CLAIMED") == 1, resultados
    # El dinero se movió exactamente una vez.
    assert saldo_en_bd(engine, "ana") == 70_00
    assert saldo_en_bd(engine, "luis") == 30_00
    comprobar_reconciliacion(engine)
