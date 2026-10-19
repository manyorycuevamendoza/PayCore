"""H9. Limitación de peticiones y tope de tamaño de cuerpo.

Mitiga API4:2023 (Unrestricted Resource Consumption) y, en la transferencia,
API6:2023 (Unrestricted Access to Sensitive Business Flows).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine

from tests.conftest import financiar, registrar, saldo_en_bd

pytestmark = [pytest.mark.integration, pytest.mark.security]


# --- El cubo de fichas, como unidad ----------------------------------------


@pytest.mark.unit
def test_el_cubo_permite_la_rafaga_y_despues_corta() -> None:
    from app.platform.rate_limit import TokenBucket

    cubo = TokenBucket(capacity=3, refill_per_second=1.0)
    ahora = 1_000.0
    assert [cubo.consume(ahora)[0] for _ in range(5)] == [True, True, True, False, False]


@pytest.mark.unit
def test_el_cubo_se_rellena_con_el_tiempo() -> None:
    from app.platform.rate_limit import TokenBucket

    cubo = TokenBucket(capacity=3, refill_per_second=1.0)
    ahora = 1_000.0
    for _ in range(3):
        cubo.consume(ahora)
    assert cubo.consume(ahora)[0] is False

    permitido, _ = cubo.consume(ahora + 2.0)
    assert permitido is True


@pytest.mark.unit
def test_el_cubo_dice_cuanto_falta_para_la_siguiente_ficha() -> None:
    from app.platform.rate_limit import TokenBucket

    cubo = TokenBucket(capacity=1, refill_per_second=0.5)  # una cada 2 s
    ahora = 1_000.0
    assert cubo.consume(ahora)[0] is True
    permitido, espera = cubo.consume(ahora)
    assert permitido is False
    assert espera == pytest.approx(2.0)


@pytest.mark.unit
def test_el_limitador_no_acumula_claves_sin_limite() -> None:
    """Sin purga, rotar la IP haría crecer el diccionario indefinidamente,
    que es el mismo problema de consumo de recursos que queremos evitar."""
    from app.platform.rate_limit import RateLimiter

    limitador = RateLimiter(
        capacity=1, refill_per_second=1.0, idle_eviction_seconds=10.0
    )
    ahora = 1_000.0
    for indice in range(50):
        limitador.check(f"ip-{indice}", now=ahora)
    assert len(limitador._buckets) == 50

    limitador.check("ip-nueva", now=ahora + 100)
    assert len(limitador._buckets) == 1


@pytest.mark.unit
def test_cada_clave_tiene_su_propio_cubo() -> None:
    from app.platform.rate_limit import RateLimiter

    limitador = RateLimiter(capacity=1, refill_per_second=1.0)
    ahora = 1_000.0
    assert limitador.check("ana", now=ahora)[0] is True
    assert limitador.check("ana", now=ahora)[0] is False
    # Luis no paga el consumo de Ana.
    assert limitador.check("luis", now=ahora)[0] is True


# --- Aplicado a los endpoints ----------------------------------------------


def test_el_login_corta_tras_la_rafaga(cliente, activar_rate_limit) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    activar_rate_limit()

    codigos = []
    for _ in range(12):
        respuesta = cliente.post(
            "/api/v1/auth/login",
            json={"email": ana.email, "password": "ContrasenaIncorrecta"},
        )
        codigos.append(respuesta.status_code)

    assert 429 in codigos, codigos
    limitada = next(
        c for c in [cliente.post("/api/v1/auth/login",
                                 json={"email": ana.email, "password": "x" * 12})]
    )
    assert limitada.status_code == 429
    cuerpo = limitada.json()["error"]
    assert cuerpo["code"] == "rate_limit_exceeded"
    # El cliente recibe cuándo volver a intentarlo.
    assert int(limitada.headers["Retry-After"]) >= 1


def test_la_transferencia_se_limita_por_usuario_y_no_por_origen(
    cliente, engine: Engine, activar_rate_limit
) -> None:
    """Limitar la transferencia por IP castigaría a toda una red compartida.
    Aquí ya sabemos quién es quien pide, así que la clave correcta es el usuario.
    """
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    luis = registrar(cliente, alias="luis", nombre="Luis Rojas")
    registrar(cliente, alias="rosa", nombre="Rosa Mamani")
    financiar(ana, 1000_00)
    financiar(luis, 1000_00)
    activar_rate_limit()

    codigos_ana = []
    for _ in range(14):
        respuesta = cliente.post(
            "/api/v1/transfers",
            headers={**ana.auth, "Idempotency-Key": str(uuid.uuid4())},
            json={"destination_alias": "rosa", "amount_cents": 1_00},
        )
        codigos_ana.append(respuesta.status_code)

    assert 429 in codigos_ana, codigos_ana

    # Luis, desde la misma IP, no está limitado: la clave es el usuario.
    de_luis = cliente.post(
        "/api/v1/transfers",
        headers={**luis.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"destination_alias": "rosa", "amount_cents": 1_00},
    )
    assert de_luis.status_code == 201

    # Las que sí pasaron movieron dinero de verdad; las 429 no movieron nada.
    aprobadas = codigos_ana.count(201)
    assert saldo_en_bd(engine, "ana") == 1000_00 - aprobadas * 1_00


def test_una_peticion_limitada_no_mueve_dinero(
    cliente, engine: Engine, activar_rate_limit
) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")
    financiar(ana, 1000_00)
    activar_rate_limit()

    for _ in range(30):
        cliente.post(
            "/api/v1/transfers",
            headers={**ana.auth, "Idempotency-Key": str(uuid.uuid4())},
            json={"destination_alias": "luis", "amount_cents": 1_00},
        )

    saldo_tras_saturar = saldo_en_bd(engine, "ana")
    limitada = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"destination_alias": "luis", "amount_cents": 1_00},
    )
    assert limitada.status_code == 429
    assert saldo_en_bd(engine, "ana") == saldo_tras_saturar


def test_la_consulta_de_saldo_no_esta_limitada(
    cliente, activar_rate_limit
) -> None:
    """Solo se limita lo que cuesta: login y transferencia. Limitar una lectura
    barata molestaría al usuario sin mitigar nada relevante."""
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    activar_rate_limit()
    for _ in range(40):
        assert (
            cliente.get("/api/v1/accounts/me/balance", headers=ana.auth).status_code
            == 200
        )


# --- Tope de tamaño de cuerpo ----------------------------------------------


def test_un_cuerpo_desmesurado_se_rechaza_con_413(cliente) -> None:
    ana = registrar(cliente, alias="ana", nombre="Ana Quispe")
    registrar(cliente, alias="luis", nombre="Luis Rojas")

    respuesta = cliente.post(
        "/api/v1/transfers",
        headers={**ana.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "destination_alias": "luis",
            "amount_cents": 1_00,
            "concept": "A" * 100_000,
        },
    )
    assert respuesta.status_code == 413
    error = respuesta.json()["error"]
    assert error["code"] == "payload_too_large"
    assert error["details"]["max_bytes"] == 16 * 1024
