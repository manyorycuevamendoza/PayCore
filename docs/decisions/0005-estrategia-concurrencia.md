# ADR-0005. Bloqueo pesimista ordenado por defecto, con `SERIALIZABLE` como alternativa medible

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

Dos transferencias simultáneas desde la misma cuenta pueden leer el mismo saldo y ambas considerarse válidas (lost update). El nivel por defecto de PostgreSQL, Read Committed, **no** impide este escenario por sí solo. Además, dos transferencias cruzadas (Ana a Luis y Luis a Ana) pueden provocar un deadlock si los bloqueos se adquieren en orden distinto.

## Decisión

Se implementan **dos estrategias** seleccionables con `PAYCORE_CONCURRENCY_STRATEGY`:

1. **`pessimistic` (por defecto).** Read Committed + `SELECT ... FOR UPDATE` sobre las filas de ambas cuentas, adquiridas siempre **en orden ascendente de `id`**. El orden determinista elimina la espera circular, que es la defensa que la propia documentación de PostgreSQL recomienda: "la mejor defensa contra los deadlocks es generalmente evitarlos asegurándose de que todas las aplicaciones adquieran los bloqueos sobre múltiples objetos en un orden consistente".
2. **`serializable`.** Nivel `SERIALIZABLE` con reintento ante SQLSTATE 40001, hasta 3 intentos, con backoff exponencial y jitter. La documentación de PostgreSQL indica explícitamente que una aplicación que use este nivel debe tener "una forma generalizada de manejar los fallos de serialización".

Independientemente de la estrategia, `CHECK (balance_cents >= 0)` actúa como última línea de defensa en el motor.

## Alternativas descartadas

- **`UPDATE ... WHERE balance >= :amt` como única defensa.** Correcto y atómico, pero mezcla validación con escritura y encaja mal con un flujo que debe insertar asientos y producir mensajes de error de negocio distintos.
- **Cola serializada por cuenta.** Elimina la contención, pero exige un broker o una tabla de cola y latencia añadida. No justificado en este alcance.
- **`threading.Lock` de Python.** No funciona entre procesos ni entre réplicas. El estado compartido vive en PostgreSQL y la garantía debe vivir donde vive el estado.

## Consecuencias

**Positivas.** El modo por defecto es predecible y sin reintentos. Tener las dos estrategias convierte la elección en un experimento con datos propios en lugar de en una preferencia.

**Negativas.** Dos caminos de código que mantener y probar. Se acepta porque el segundo es el objeto del experimento de la Fase 7 y no una duplicación accidental.

**Hipótesis a contrastar.** Bajo la contención máxima de la Prueba D (cien peticiones sobre la misma cuenta) se espera que el pesimista supere al optimista, porque el optimista degeneraría en abortos y reintentos. *Pendiente de medición, Fase 7.* No se afirmará nada al respecto hasta tener los CSV.
