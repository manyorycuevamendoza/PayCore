"""H1. La API arranca y responde la sonda de salud."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.conftest import TEST_URL

pytestmark = pytest.mark.integration


@pytest.fixture
def cliente(engine: Engine):
    os.environ["PAYCORE_DATABASE_URL"] = TEST_URL
    from app.platform import config, db

    config.get_settings.cache_clear()
    db.reset_engine()

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c

    db.reset_engine()
    config.get_settings.cache_clear()


def test_health_responde_ok(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["database"] == "ok"
    assert cuerpo["concurrency_strategy"] in {"pessimistic", "serializable"}


def test_toda_respuesta_lleva_identificador_de_correlacion(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/health")
    assert respuesta.headers.get("X-Request-ID")


def test_se_respeta_el_identificador_de_correlacion_del_cliente(
    cliente: TestClient,
) -> None:
    respuesta = cliente.get(
        "/api/v1/health", headers={"X-Request-ID": "trazabilidad-de-prueba"}
    )
    assert respuesta.headers["X-Request-ID"] == "trazabilidad-de-prueba"


def test_la_especificacion_openapi_se_genera(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/openapi.json")
    assert respuesta.status_code == 200
    especificacion = respuesta.json()
    assert especificacion["info"]["title"] == "PayCore API"
    assert "/api/v1/health" in especificacion["paths"]


def test_una_ruta_inexistente_devuelve_el_formato_de_error_uniforme(
    cliente: TestClient,
) -> None:
    respuesta = cliente.get("/api/v1/no-existe")
    assert respuesta.status_code == 404
    error = respuesta.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"]
    # Ninguna respuesta de error expone traza interna.
    assert "Traceback" not in respuesta.text
