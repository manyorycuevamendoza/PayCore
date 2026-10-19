"""H7. Prueba D del enunciado y ausencia de deadlocks.

Se atacan los servicios con hilos y conexiones reales contra PostgreSQL. Lo
que se verifica es una garantía del motor, por lo que las aserciones miran el
estado final de la base de datos y nunca una respuesta HTTP.
"""

from __future__ import annotations

import threading
import uuid
from collections import Counter

import pytest
from sqlalchemy import Engine, text

from app.platform.config import ConcurrencyStrategy
from tests.conftest import comprobar_reconciliacion, financiar, registrar, saldo_en_bd

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


def _intentar_transferencia(
    *,
    user_id: uuid.UUID,
    destino: str,
    importe_cents: int,
    strategy: ConcurrencyStrategy,
) -> str:
    """Un intento completo de transferencia en su propia transacción."""
    from app.modules.accounts import service as accounts_service
    from app.modules.transfers import service as transfers_service
    from app.platform.db import transactional
    from app.platform.errors import ConcurrencyRetryExhaustedError

    def operacion(session) -> str:
        origen = accounts_service.get_by_user(session, user_id)
        resultado = transfers_service.execute_transfer(
            session,
            source_account_id=origen.id,
            destination_alias=destino,
            amount_cents=importe_cents,
            strategy=strategy,
        )
        return "completed" if resultado.completed else "rejected"

    try:
        return transactional(operacion, strategy=strategy)
    except ConcurrencyRetryExhaustedError:
        return "retry_exhausted"
    except Exception as error:  # noqa: BLE001
        return f"error:{type(error).__name__}"


def _lanzar_en_paralelo(objetivo, veces: int) -> Counter[str]:
    """Arranca `veces` hilos que salen a la vez desde una barrera."""
    barrera = threading.Barrier(veces, timeout=60)
    resultados: list[str] = []
    cerrojo = threading.Lock()

    def envoltura() -> None:
        try:
            barrera.wait()
            salida = objetivo()
        except Exception as error:  # noqa: BLE001
            salida = f"error:{type(error).__name__}"
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=envoltura) for _ in range(veces)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=180)

    assert len(resultados) == veces, f"Hilos sin terminar: {veces - len(resultados)}"
    return Counter(resultados)


# --- Prueba D. Cien solicitudes concurrentes -------------------------------


@pytest.mark.parametrize(
    "strategy",
    [ConcurrencyStrategy.PESSIMISTIC, ConcurrencyStrategy.SERIALIZABLE],
    ids=["pesimista", "serializable"],
)
def test_prueba_d_cien_solicitudes_concurrentes(
    cliente, engine: Engine, strategy: ConcurrencyStrategy, capsys
) -> None:
    """Una cuenta tiene S/100. Cien solicitudes intentan transferir S/30.

    Resultado esperado: como máximo tres aprobadas. Las solicitudes son todas
    válidas y distintas, y el sistema completa su procesamiento, así que lo
    correcto es que se aprueben tres y se rechacen el resto.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    conteo = _lanzar_en_paralelo(
        lambda: _intentar_transferencia(
            user_id=ana.user_id,
            destino="luis",
            importe_cents=30_00,
            strategy=strategy,
        ),
        veces=100,
    )

    aprobadas = conteo["completed"]
    saldo_final = saldo_en_bd(engine, "ana")

    with capsys.disabled():
        print(f"\n  [{strategy.value}] resultados de 100 intentos: {dict(conteo)}")
        print(f"  [{strategy.value}] saldo final de Ana: {saldo_final} céntimos")

    # La garantía dura: nunca más de tres, nunca saldo negativo.
    assert aprobadas <= 3, f"Se aprobaron {aprobadas} transferencias de 30 sobre 100"
    assert saldo_final >= 0
    # El saldo es exactamente el que explican las transferencias aprobadas.
    assert saldo_final == 100_00 - aprobadas * 30_00
    assert saldo_en_bd(engine, "luis") == aprobadas * 30_00

    # Nunca se produce un deadlock: el orden de bloqueo lo impide.
    assert conteo["error:OperationalError"] == 0

    # El número de pares de asientos coincide con las aprobadas.
    with engine.connect() as conn:
        asientos = conn.execute(
            text("SELECT count(*) FROM ledger_entries")
        ).scalar_one()
        completadas = conn.execute(
            text("SELECT count(*) FROM transfers WHERE status = 'completed'")
        ).scalar_one()
    # Una transferencia es la carga inicial de saldo.
    assert completadas == aprobadas + 1
    assert asientos == (aprobadas + 1) * 2

    comprobar_reconciliacion(engine)


def test_la_estrategia_pesimista_aprueba_exactamente_tres(
    cliente, engine: Engine
) -> None:
    """Con bloqueo pesimista las cien peticiones forman cola y ninguna se pierde.

    Se afirma la igualdad exacta, y no solo el "como máximo tres", porque el
    modo por defecto no aborta transacciones: cada intento llega a evaluarse
    contra el saldo real del momento.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 100_00)

    conteo = _lanzar_en_paralelo(
        lambda: _intentar_transferencia(
            user_id=ana.user_id,
            destino="luis",
            importe_cents=30_00,
            strategy=ConcurrencyStrategy.PESSIMISTIC,
        ),
        veces=100,
    )

    assert conteo["completed"] == 3
    assert conteo["rejected"] == 97
    assert saldo_en_bd(engine, "ana") == 10_00
    comprobar_reconciliacion(engine)


# --- Ausencia de deadlocks -------------------------------------------------


def test_transferencias_cruzadas_no_producen_deadlock(
    cliente, engine: Engine
) -> None:
    """Ana envía a Luis mientras Luis envía a Ana, muchas veces a la vez.

    Sin un orden de bloqueo común esto es el ejemplo de libro de espera
    circular. Con el orden ascendente de identificador de ADR-0005, no puede
    ocurrir. Un deadlock se manifestaría como OperationalError con SQLSTATE
    40P01, que `transactional` deliberadamente NO reintenta para que un fallo
    de diseño no quede enmascarado.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 500_00)
    financiar(luis, 500_00)

    parejas = [(ana.user_id, "luis"), (luis.user_id, "ana")] * 25

    barrera = threading.Barrier(len(parejas), timeout=60)
    resultados: list[str] = []
    cerrojo = threading.Lock()

    def intentar(user_id: uuid.UUID, destino: str) -> None:
        try:
            barrera.wait()
            salida = _intentar_transferencia(
                user_id=user_id,
                destino=destino,
                importe_cents=1_00,
                strategy=ConcurrencyStrategy.PESSIMISTIC,
            )
        except Exception as error:  # noqa: BLE001
            salida = f"error:{type(error).__name__}"
        with cerrojo:
            resultados.append(salida)

    hilos = [
        threading.Thread(target=intentar, args=(user_id, destino))
        for user_id, destino in parejas
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=120)

    conteo = Counter(resultados)
    assert conteo["completed"] == len(parejas), dict(conteo)

    # 25 envíos de ida y 25 de vuelta de S/1: los saldos vuelven al origen.
    assert saldo_en_bd(engine, "ana") == 500_00
    assert saldo_en_bd(engine, "luis") == 500_00
    comprobar_reconciliacion(engine)


def test_transferencias_concurrentes_entre_cuentas_distintas_no_se_estorban(
    cliente, engine: Engine
) -> None:
    """Bloquear por fila y no por tabla: cuentas distintas avanzan en paralelo."""
    personas = []
    for indice in range(10):
        persona = registrar(
            cliente, alias=f"persona{indice}", nombre=f"Persona {indice}"
        )
        financiar(persona, 100_00)
        personas.append(persona)

    destino = registrar(cliente, alias="caja", nombre="Caja Comun")

    conteos = _lanzar_en_paralelo(
        lambda: "sin-uso", veces=1
    )  # calienta el pool antes de medir
    assert conteos

    barrera = threading.Barrier(len(personas), timeout=60)
    resultados: list[str] = []
    cerrojo = threading.Lock()

    def intentar(persona) -> None:
        barrera.wait()
        salida = _intentar_transferencia(
            user_id=persona.user_id,
            destino="caja",
            importe_cents=10_00,
            strategy=ConcurrencyStrategy.PESSIMISTIC,
        )
        with cerrojo:
            resultados.append(salida)

    hilos = [threading.Thread(target=intentar, args=(p,)) for p in personas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert Counter(resultados)["completed"] == len(personas)
    assert saldo_en_bd(engine, "caja") == len(personas) * 10_00
    for persona in personas:
        assert saldo_en_bd(engine, persona.alias) == 90_00
    comprobar_reconciliacion(engine)
    assert destino.alias == "caja"
