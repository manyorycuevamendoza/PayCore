# ADR-0002. PostgreSQL 16 como motor de base de datos

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

El proyecto necesita garantías ACID reales, dos estrategias de concurrencia comparables en el mismo motor, tipos exactos para dinero y restricciones a nivel de esquema.

## Decisión

PostgreSQL 16.

## Justificación

- `SELECT ... FOR UPDATE` con semántica y recomendaciones de orden de bloqueo documentadas (PostgreSQL 16, cap. 13.3).
- `SERIALIZABLE` genuino mediante Serializable Snapshot Isolation, implementación descrita en Ports y Grittner, PVLDB 5(12), 2012, que reporta un coste de menos del 7% frente a snapshot isolation.
- SQLSTATE 40001 documentado como señal estándar de reintento (cap. 13.2).
- Durabilidad por WAL (cap. 29.3).
- Restricciones `CHECK` que permiten que "ningún saldo negativo" sea una garantía del motor y no una promesa del framework.
- Tipos exactos y advertencia explícita contra el punto flotante para dinero (cap. 8.2).

## Alternativas descartadas

- **MySQL/InnoDB:** sin SSI, su `SERIALIZABLE` se apoya en bloqueo. Comparar las dos estrategias sería comparar motores, no estrategias.
- **SQLite:** la concurrencia de escritura es a nivel de fichero. La Prueba D dejaría de medir lo que pretende medir.
- **MongoDB:** transacciones multidocumento disponibles pero con más condiciones, y sin `CHECK` de columna.

## Consecuencias

Punto único de fallo y techo de escritura de un nodo, aceptados y declarados. Coste operativo real de PostgreSQL en producción (vacuum, réplicas, failover) que este prototipo no asume y que se documenta como limitación.
