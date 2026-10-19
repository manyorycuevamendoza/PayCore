# ADR-0005. Bloqueo pesimista ordenado por defecto, con `SERIALIZABLE` como alternativa medible

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

Dos transferencias simultáneas desde la misma cuenta pueden leer el mismo saldo y ambas considerarse válidas (lost update). El nivel por defecto de PostgreSQL, Read Committed, **no** impide este escenario por sí solo. Además, dos transferencias cruzadas (Ana a Luis y Luis a Ana) pueden provocar un deadlock si los bloqueos se adquieren en orden distinto.

## Decisión

Se implementan **dos estrategias** seleccionables con `PAYCORE_CONCURRENCY_STRATEGY`:

1. **`pessimistic` (por defecto).** Read Committed + `SELECT ... FOR UPDATE` sobre las filas de ambas cuentas, adquiridas siempre **en orden ascendente de `id`**. El orden determinista elimina la espera circular, que es la defensa que la propia documentación de PostgreSQL recomienda: "la mejor defensa contra los deadlocks es generalmente evitarlos asegurándose de que todas las aplicaciones adquieran los bloqueos sobre múltiples objetos en un orden consistente".
2. **`serializable`.** Nivel `SERIALIZABLE` con reintento ante SQLSTATE 40001, hasta 3 intentos, con backoff exponencial y jitter. **No toma bloqueos de fila**: la detección de conflictos la hace el SSI de PostgreSQL. Tomar `FOR UPDATE` aquí también haría que las dos estrategias dejaran de ser distinguibles y el experimento no mediría nada. La documentación de PostgreSQL indica explícitamente que una aplicación que use este nivel debe tener "una forma generalizada de manejar los fallos de serialización".

Independientemente de la estrategia, `CHECK (balance_cents >= 0)` actúa como última línea de defensa en el motor.

## Alternativas descartadas

- **`UPDATE ... WHERE balance >= :amt` como única defensa.** Correcto y atómico, pero mezcla validación con escritura y encaja mal con un flujo que debe insertar asientos y producir mensajes de error de negocio distintos.
- **Cola serializada por cuenta.** Elimina la contención, pero exige un broker o una tabla de cola y latencia añadida. No justificado en este alcance.
- **`threading.Lock` de Python.** No funciona entre procesos ni entre réplicas. El estado compartido vive en PostgreSQL y la garantía debe vivir donde vive el estado.

## Consecuencias

**Positivas.** El modo por defecto es predecible y sin reintentos. Tener las dos estrategias convierte la elección en un experimento con datos propios en lugar de en una preferencia.

**Negativas.** Dos caminos de código que mantener y probar. Se acepta porque el segundo es el objeto del experimento de la Fase 7 y no una duplicación accidental.

**Hipótesis contrastada (18 de octubre de 2026).** Se esperaba que bajo la contención máxima de la Prueba D (cien peticiones sobre la misma cuenta) el optimista degenerara en abortos y reintentos. Medido en tres ejecuciones:

| Estrategia | Aprobadas | Rechazo de negocio | Reintentos agotados (503) |
|---|---|---|---|
| `pessimistic` | 3, 3, 3 | 97, 97, 97 | 0, 0, 0 |
| `serializable` | 3, 3, 3 | 94, 92, 93 | 3, 5, 4 |

Las dos son correctas: siempre 3 aprobadas, saldo final 1000 céntimos, ningún saldo negativo y reconciliación cuadrada. Se diferencian en la calidad del rechazo: el pesimista da a todas las peticiones una respuesta de negocio ("fondos insuficientes"), mientras que `SERIALIZABLE` devuelve un 503 a entre el 3% y el 5% de ellas, que no dice nada sobre su dinero. Se confirma la elección por defecto. Detalle en [docs/evidence/h7-h8-pruebas.md](../evidence/h7-h8-pruebas.md).

Las cifras de throughput y latencia bajo carga sostenida son otra medición distinta y se harán con Locust en la Fase 7.

**Trampa encontrada al implementar, y que esta decisión no había previsto.** Tomar el bloqueo correcto en SQL no basta. Si el caso de uso lee la cuenta **sin** bloqueo antes de volver a leerla **con** bloqueo, el mapa de identidad de SQLAlchemy devuelve el objeto ya cargado sin refrescar sus atributos: la sentencia `FOR UPDATE` se ejecuta y el bloqueo se adquiere, pero la lógica de negocio evalúa el saldo obsoleto. Con el fallo presente, la Prueba D aprobaba 88 transferencias de 100 y las 76 pruebas de un solo hilo pasaban todas. La corrección es `execution_options(populate_existing=True)` sobre la consulta de bloqueo.
