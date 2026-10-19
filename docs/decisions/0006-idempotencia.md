# ADR-0006. Idempotencia persistida en la misma transacción que el movimiento de dinero

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

Si la respuesta se pierde después de que el servidor haya confirmado la transferencia, el cliente no sabe si el dinero se movió. Reintentar sin protección duplica el pago. Ninguna propiedad ACID cubre esto, porque el problema está fuera del límite de la transacción.

## Decisión

Tabla `idempotency_keys` en PostgreSQL con `UNIQUE (user_id, key)`, huella SHA-256 del método, la ruta y el cuerpo canonicalizado, y estado `in_progress` / `succeeded` / `failed`.

Protocolo:

1. `INSERT ... ON CONFLICT DO NOTHING` reclama la clave de forma atómica.
2. Si se reclamó, la transferencia y la escritura de la respuesta ocurren en **la misma transacción**. Un único `COMMIT` cubre asientos, saldos y clave.
3. Si no se reclamó: misma huella y estado finalizado, se reproduce la respuesta almacenada con cabecera `Idempotent-Replay: true`; misma huella y `in_progress`, **409 Conflict**; huella distinta, **422 Unprocessable Content**.
4. TTL de 24 horas con purga documentada y ejecutable.

El ámbito es **por usuario autenticado**, no global.

## Justificación de cada elección

- **Misma transacción.** Si la clave se escribiera después del `COMMIT` del dinero, una caída entre ambos pasos dejaría una transferencia ejecutada sin registro, y el reintento la duplicaría. Compartir transacción cierra esa ventana por completo.
- **409 y 422.** Son los códigos que recomienda `draft-ietf-httpapi-idempotency-key-header-07` (IETF HTTPAPI WG, revisión de 15 de octubre de 2025, actualmente expirado, por lo que se cita como práctica emergente y no como estándar).
- **TTL de 24 horas.** Alineado con la política publicada de Stripe para su API v1.
- **Ámbito por usuario.** Evita colisiones entre clientes y, sobre todo, impide que un usuario reutilice la clave de otro para obtener su respuesta almacenada. Es una propiedad de seguridad, no solo de corrección.

## Alternativas descartadas

- **Deduplicación por ventana temporal.** Heurística: rechaza transferencias legítimas repetidas y no cubre reintentos tardíos.
- **Clave en memoria del proceso.** Se pierde al reiniciar y no se comparte entre workers.
- **Clave en Redis.** Rompe la atomicidad al poner la clave y el dinero en sistemas distintos, reintroduciendo exactamente la ventana que el diseño cierra.

## Consecuencias

Una tabla adicional, una política de purga y la obligación de que el caso de uso de transferencia gestione los tres caminos de reentrada. Se verifica con la Prueba C (reintento secuencial), una prueba de reentrada concurrente con la misma clave y la Prueba E (fallo después del `COMMIT`).
