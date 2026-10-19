"""Limitación de peticiones por cubo de fichas (token bucket).

Mitiga API4:2023, Unrestricted Resource Consumption, y API6:2023 en el caso de
la transferencia, que es el flujo de negocio sensible.

LIMITACIÓN IMPORTANTE Y DELIBERADA: el contador vive en memoria del proceso.
Con varios workers o varias réplicas, el límite efectivo se multiplica por el
número de procesos. Resolverlo bien exige un contador compartido, y esa es
exactamente la condición de reingreso de Redis documentada en docs/stack.md.
Mientras el despliegue sea de un proceso, esto es correcto; en cuanto deje de
serlo, deja de serlo. Está declarado en ADR-0009 y en el README en lugar de
presentarse como una defensa que no es.

Se elige cubo de fichas y no ventana fija porque la ventana fija permite el
doble del límite a caballo entre dos ventanas: 5 peticiones al final de una y
5 al principio de la siguiente son 10 en un instante.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: float          # ráfaga máxima
    refill_per_second: float # ritmo sostenido
    tokens: float = field(init=False)
    updated_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.updated_at = time.monotonic()

    def consume(self, now: float, amount: float = 1.0) -> tuple[bool, float]:
        """Intenta consumir una ficha.

        Devuelve (permitido, segundos que faltan para la siguiente ficha).
        """
        transcurrido = max(0.0, now - self.updated_at)
        self.tokens = min(
            self.capacity, self.tokens + transcurrido * self.refill_per_second
        )
        self.updated_at = now

        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0.0

        faltan = amount - self.tokens
        return False, faltan / self.refill_per_second


class RateLimiter:
    """Cubos por clave, con purga de los inactivos.

    Sin purga, un atacante que rote la IP haría crecer el diccionario sin
    límite, que es el mismo problema de consumo de recursos que esta clase
    pretende evitar.
    """

    def __init__(
        self,
        *,
        capacity: float,
        refill_per_second: float,
        idle_eviction_seconds: float = 900.0,
        max_keys: int = 10_000,
    ) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.idle_eviction_seconds = idle_eviction_seconds
        self.max_keys = max_keys
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        instante = time.monotonic() if now is None else now
        with self._lock:
            self._evict(instante)
            cubo = self._buckets.get(key)
            if cubo is None:
                cubo = TokenBucket(
                    capacity=self.capacity, refill_per_second=self.refill_per_second
                )
                cubo.updated_at = instante
                self._buckets[key] = cubo
            return cubo.consume(instante)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _evict(self, now: float) -> None:
        if len(self._buckets) < self.max_keys:
            caducados = [
                clave
                for clave, cubo in self._buckets.items()
                if now - cubo.updated_at > self.idle_eviction_seconds
            ]
        else:
            # Presión de memoria: se descartan los menos recientes.
            caducados = sorted(
                self._buckets, key=lambda c: self._buckets[c].updated_at
            )[: len(self._buckets) // 2]
        for clave in caducados:
            self._buckets.pop(clave, None)
