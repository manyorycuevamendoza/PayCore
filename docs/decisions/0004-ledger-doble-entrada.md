# ADR-0004. Ledger de doble entrada como fuente de verdad, con saldo materializado

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

El saldo puede modelarse como una columna mutable, como la suma de un histórico de asientos, o como ambas cosas. La opción elegida determina si el sistema es auditable y si el cuadre es verificable de forma independiente al código que lo produce.

## Decisión

- `ledger_entries` es **append-only** y es la **fuente de verdad**. Cada transferencia completada genera exactamente dos asientos: uno negativo en el origen y uno positivo en el destino, de igual magnitud y ligados por `transfer_id`.
- `accounts.balance_cents` es una **proyección materializada** del ledger, escrita en la misma transacción que los asientos.
- El origen del dinero simulado es una cuenta de sistema `SYSTEM_FUNDING`, exenta de la restricción de no negatividad, de modo que la suma global de asientos es exactamente cero incluso tras la carga de datos de prueba.

## Alternativas descartadas

- **Solo columna mutable.** Sin auditoría. Un error sobrescribe el saldo sin dejar rastro y el cuadre no es verificable.
- **Solo ledger, saldo calculado al vuelo.** Auditable, pero la lectura es O(n) creciente y aplicar "saldo no negativo" de forma atómica exige agregar el histórico bajo bloqueo en cada transferencia.

## Consecuencias

**Positivas.** Lectura de saldo O(1). Rastro de auditoría completo. Existe una fila concreta sobre la que adquirir el bloqueo. `CHECK (balance_cents >= 0)` es posible porque hay una columna que restringir.

**Negativas.** Dos representaciones que deben coincidir. Se acepta con dos contrapartidas obligatorias: escribir ambas en la misma transacción, y una **prueba de reconciliación** que recalcula desde el ledger y se ejecuta al final de cada suite y después de cada prueba de carga.

**Referencias.** Fowler, *Accounting Narrative* (2006), para el patrón. Square, *Books* (2019), como caso de industria donde la partida doble se adoptó tras observar inconsistencias de datos en producción.
