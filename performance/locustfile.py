"""Escenarios de carga de PayCore.

Tres clases de usuario. Se elige una con la variable de entorno
PAYCORE_ESCENARIO, y las otras se marcan como abstractas para que Locust ni
las instancie:

  mixto      Reparto realista: lecturas y transferencias entre cuentas
             distintas elegidas al azar. Mide el rendimiento general.
  caliente   Todas las transferencias salen de la MISMA cuenta. Contención
             máxima sobre una fila: es el peor caso para el control de
             concurrencia y donde se distinguen las dos estrategias.
  lectura    Solo saldo e historial. Línea base: cuánto cuesta la
             infraestructura sin trabajo transaccional.

Las tres son clases distintas y no una sola con tareas que a veces no hacen
nada. Una primera versión sí lo hacía y falseaba la línea base: las tareas
vacías consumían turnos de planificación sin emitir peticiones, de modo que
el escenario de solo lectura parecía más lento que el mixto, que hace más
trabajo. Los números de aquel intento se descartaron.

Advertencia metodológica, repetida en docs/performance.md: Locust mide lo que
responde la API, no si el dinero quedó bien registrado. Por eso
performance/run.sh ejecuta una reconciliación contra PostgreSQL al terminar
cada carrera. Un sistema que respondiera 201 a todo sin escribir nada daría
unos números excelentes aquí.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import uuid

from locust import HttpUser, between, events, task

ESCENARIO = os.getenv("PAYCORE_ESCENARIO", "mixto")
RUTA_CUENTAS = pathlib.Path(__file__).parent / "cuentas.json"

IMPORTE_CENTS = 100  # S/ 1,00 simulado por transferencia


def _cargar_cuentas() -> tuple[list[dict], dict]:
    if not RUTA_CUENTAS.exists():
        raise RuntimeError(
            "Falta performance/cuentas.json. Ejecuta primero:\n"
            "  PYTHONPATH=backend python performance/seed_perf.py"
        )
    datos = json.loads(RUTA_CUENTAS.read_text())
    return datos["cuentas"], datos["caliente"]


CUENTAS, CALIENTE = _cargar_cuentas()


@events.test_start.add_listener
def _anunciar(environment, **_kwargs) -> None:
    print(f"\n  Escenario: {ESCENARIO}")
    print(f"  Cuentas disponibles: {len(CUENTAS)}")
    if ESCENARIO == "caliente":
        print(f"  Todas las transferencias salen de @{CALIENTE['alias']}")
    print()


class Base(HttpUser):
    abstract = True
    wait_time = between(0.0, 0.05)
    credenciales: dict[str, str]

    def elegir_credenciales(self) -> dict[str, str]:
        return random.choice(CUENTAS)

    def on_start(self) -> None:
        self.credenciales = self.elegir_credenciales()
        respuesta = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.credenciales["email"],
                "password": self.credenciales["password"],
            },
            name="POST /auth/login",
        )
        if respuesta.status_code != 200:
            # No se aborta la carrera: un login fallido es un dato, y matar la
            # ejecución falsearía el resto de la medición.
            self.cabeceras: dict[str, str] = {}
            return
        self.cabeceras = {
            "Authorization": f"Bearer {respuesta.json()['access_token']}"
        }

    # --- Operaciones reutilizables ----------------------------------------

    def leer_saldo(self) -> None:
        self.client.get(
            "/api/v1/accounts/me/balance",
            headers=self.cabeceras,
            name="GET /accounts/me/balance",
        )

    def leer_historial(self) -> None:
        self.client.get(
            "/api/v1/accounts/me/transactions?limit=10&offset=0",
            headers=self.cabeceras,
            name="GET /accounts/me/transactions",
        )

    def enviar(self, destino: str) -> None:
        with self.client.post(
            "/api/v1/transfers",
            json={"destination_alias": destino, "amount_cents": IMPORTE_CENTS},
            headers={
                **self.cabeceras,
                # Clave nueva por petición: cada una es una operación distinta.
                "Idempotency-Key": str(uuid.uuid4()),
            },
            name="POST /transfers",
            catch_response=True,
        ) as respuesta:
            if respuesta.status_code == 201:
                respuesta.success()
            elif respuesta.status_code == 422:
                # Fondos insuficientes es una respuesta correcta del negocio,
                # no un fallo del sistema. Se marca como éxito para que la
                # tasa de fallos signifique lo que debe significar.
                respuesta.success()
            elif respuesta.status_code == 503:
                # Reintentos de serialización agotados. Esto SÍ es un fallo:
                # el cliente no obtiene respuesta sobre su dinero.
                respuesta.failure("503 reintentos de serializacion agotados")
            else:
                respuesta.failure(f"inesperado {respuesta.status_code}")


class UsuarioMixto(Base):
    """Lecturas y transferencias entre cuentas al azar."""

    abstract = ESCENARIO != "mixto"

    @task(1)
    def saldo(self) -> None:
        self.leer_saldo()

    @task(1)
    def historial(self) -> None:
        self.leer_historial()

    @task(2)
    def transferencia(self) -> None:
        destino = random.choice(CUENTAS)["alias"]
        if destino == self.credenciales["alias"]:
            return
        self.enviar(destino)


class UsuarioCaliente(Base):
    """Todas las transferencias salen de la misma cuenta."""

    abstract = ESCENARIO != "caliente"

    def elegir_credenciales(self) -> dict[str, str]:
        return CALIENTE

    @task
    def transferencia(self) -> None:
        self.enviar(random.choice(CUENTAS)["alias"])


class UsuarioLectura(Base):
    """Línea base sin trabajo transaccional."""

    abstract = ESCENARIO != "lectura"

    @task(1)
    def saldo(self) -> None:
        self.leer_saldo()

    @task(1)
    def historial(self) -> None:
        self.leer_historial()
