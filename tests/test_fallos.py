"""H8. Prueba E del enunciado: fallos antes del commit, después del commit y
antes de entregar la respuesta al cliente.

Es la prueba que justifica el diseño de ADR-0006. Las tres situaciones se
provocan de verdad, no se simulan con comentarios.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from tests.conftest import comprobar_reconciliacion, financiar, registrar, saldo_en_bd

pytestmark = pytest.mark.integration


def _clave() -> str:
    return str(uuid.uuid4())


def _estado(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            "ana": conn.execute(
                text("SELECT balance_cents FROM accounts WHERE alias = 'ana'")
            ).scalar_one(),
            "luis": conn.execute(
                text("SELECT balance_cents FROM accounts WHERE alias = 'luis'")
            ).scalar_one(),
            "asientos": conn.execute(
                text("SELECT count(*) FROM ledger_entries")
            ).scalar_one(),
            "transferencias": conn.execute(
                text("SELECT count(*) FROM transfers WHERE status = 'completed'")
            ).scalar_one(),
            "claves": conn.execute(
                text("SELECT count(*) FROM idempotency_keys")
            ).scalar_one(),
        }


@pytest.fixture
def cliente_tolerante(limpiar: None):
    """Cliente que no relanza las excepciones del servidor.

    Hace falta para observar el 500 tal y como lo vería un cliente real en
    lugar de que la excepción aborte la prueba.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


# --- E1. Fallo ANTES del commit --------------------------------------------


def test_e1_un_fallo_antes_del_commit_no_deja_rastro(
    cliente_tolerante, engine: Engine, monkeypatch
) -> None:
    """Se inyecta un error justo después de mover el saldo y antes de confirmar.

    Esperado: ROLLBACK completo. Ni asientos, ni saldos movidos, ni clave de
    idempotencia registrada.
    """
    cliente = cliente_tolerante
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    antes = _estado(engine)
    clave = _clave()

    from app.modules.idempotency import service as idempotency_service

    def explotar(*_args, **_kwargs):
        raise RuntimeError("fallo inyectado justo antes del COMMIT")

    monkeypatch.setattr(idempotency_service, "finish", explotar)

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )
    assert respuesta.status_code == 500
    assert respuesta.json()["error"]["code"] == "internal_error"
    # Ni siquiera en el error se filtra el detalle interno.
    assert "fallo inyectado" not in respuesta.text

    despues = _estado(engine)
    assert despues == antes, "La transacción dejó rastro pese a no confirmarse"

    comprobar_reconciliacion(engine)

    # Y como la clave tampoco se registró, el reintento funciona con normalidad.
    monkeypatch.undo()
    reintento = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )
    assert reintento.status_code == 201
    assert saldo_en_bd(engine, "ana") == 70_00
    assert saldo_en_bd(engine, "luis") == 30_00
    comprobar_reconciliacion(engine)


# --- E2. Fallo DESPUÉS del commit, antes de responder ----------------------


def test_e2_un_fallo_tras_el_commit_no_duplica_al_reintentar(
    cliente_tolerante, engine: Engine, monkeypatch
) -> None:
    """El caso que ninguna propiedad ACID resuelve.

    El dinero ya se movió y la respuesta nunca llega al cliente. El cliente no
    sabe si pagó. Al reintentar con la misma clave debe recibir la respuesta
    original sin que se mueva nada por segunda vez.
    """
    cliente = cliente_tolerante
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    clave = _clave()
    cuerpo = {"destination_alias": "luis", "amount_cents": 30_00}

    # Se rompe la entrega de la respuesta DESPUÉS de que la transacción haya
    # confirmado, que es justo el instante en el que se pierde la respuesta por
    # un corte de red.
    from app.api.v1 import transfers as endpoint

    original = endpoint.JSONResponse

    def responder_roto(*_args, **_kwargs):
        raise RuntimeError("la conexión se cayó al entregar la respuesta")

    monkeypatch.setattr(endpoint, "JSONResponse", responder_roto)

    perdida = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json=cuerpo,
    )
    assert perdida.status_code == 500

    # El dinero SÍ se movió: la transacción se confirmó antes del fallo.
    assert saldo_en_bd(engine, "ana") == 70_00
    assert saldo_en_bd(engine, "luis") == 30_00
    estado_tras_la_perdida = _estado(engine)
    assert estado_tras_la_perdida["asientos"] == 4  # carga inicial + transferencia

    # El cliente, que no sabe nada, reintenta con la misma clave.
    monkeypatch.setattr(endpoint, "JSONResponse", original)
    reintento = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": clave},
        json=cuerpo,
    )

    assert reintento.status_code == 201
    assert reintento.headers.get("Idempotent-Replay") == "true"
    # Nada se movió por segunda vez.
    assert _estado(engine) == estado_tras_la_perdida
    assert saldo_en_bd(engine, "ana") == 70_00
    comprobar_reconciliacion(engine)


def test_e2_sin_clave_de_idempotencia_el_reintento_si_duplicaria(
    cliente_tolerante, engine: Engine
) -> None:
    """Contraprueba: dos peticiones con claves distintas sí mueven dos veces.

    Sirve para dejar claro que lo que evita el duplicado es la clave y no
    ninguna otra propiedad del sistema.
    """
    cliente = cliente_tolerante
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    cuerpo = {"destination_alias": "luis", "amount_cents": 30_00}
    for _ in range(2):
        respuesta = cliente.post(
            "/api/v1/transfers",
            headers={**ana.auth, "Idempotency-Key": _clave()},
            json=cuerpo,
        )
        assert respuesta.status_code == 201

    assert saldo_en_bd(engine, "ana") == 40_00
    assert saldo_en_bd(engine, "luis") == 60_00
    comprobar_reconciliacion(engine)


# --- E3. Caída real del proceso de base de datos ---------------------------


def test_e3_si_se_corta_la_conexion_a_mitad_la_transaccion_se_deshace(
    cliente, engine: Engine
) -> None:
    """No se simula el fallo: se mata el proceso servidor de la transacción.

    Con pg_terminate_backend desde otra conexión, PostgreSQL aborta el backend
    que estaba a mitad de la transferencia. Es lo más parecido a un corte de
    luz que se puede provocar de forma reproducible.
    """
    from sqlalchemy.exc import DBAPIError

    from app.modules.accounts import service as accounts_service
    from app.modules.transfers import service as transfers_service
    from app.platform.db import unit_of_work

    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    antes = _estado(engine)

    with pytest.raises(DBAPIError):
        with unit_of_work() as session:
            pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()

            origen = accounts_service.get_by_user(session, ana.user_id)
            transfers_service.execute_transfer(
                session,
                source_account_id=origen.id,
                destination_alias="luis",
                amount_cents=30_00,
            )
            # Los asientos y los saldos ya están escritos, pero sin confirmar.
            # Ahora se mata el backend desde fuera.
            with engine.connect() as verdugo:
                verdugo.execute(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                )
                verdugo.commit()
            # Al salir del with, el COMMIT falla contra una conexión muerta.

    despues = _estado(engine)
    assert despues == antes, "Quedó estado a medias tras matar la conexión"
    assert saldo_en_bd(engine, "ana") == 100_00
    assert saldo_en_bd(engine, "luis") == 0
    comprobar_reconciliacion(engine)


def test_e3_el_servicio_sigue_operativo_tras_la_caida(
    cliente, engine: Engine
) -> None:
    """Tras matar una conexión, el pool se recupera y la siguiente va bien.

    pool_pre_ping descarta las conexiones muertas antes de usarlas.
    """
    from sqlalchemy.exc import DBAPIError

    from app.platform.db import unit_of_work

    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    with pytest.raises(DBAPIError):
        with unit_of_work() as session:
            pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            with engine.connect() as verdugo:
                verdugo.execute(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                )
                verdugo.commit()
            session.execute(text("SELECT 1"))

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": _clave()},
        json={"destination_alias": "luis", "amount_cents": 30_00},
    )
    assert respuesta.status_code == 201
    assert saldo_en_bd(engine, "ana") == 70_00
    comprobar_reconciliacion(engine)
