# Evidencia de ejecución: hitos H7 y H8

Ejecutado el 18 de octubre de 2026. Python 3.12.3, PostgreSQL 16.10-alpine en
contenedor, Linux 7.0.0-34-generic.

Cubre las pruebas D (concurrencia) y E (fallos) del enunciado.

---

## Un lost update real, encontrado por la Prueba D

La primera ejecución de la Prueba D con estrategia pesimista aprobó **88
transferencias de 100**, cuando el máximo posible era 3.

El bloqueo `SELECT ... FOR UPDATE` se estaba tomando correctamente. El fallo
estaba una capa más arriba, en el mapa de identidad de SQLAlchemy: el caso de
uso leía la cuenta de origen **sin bloqueo** (`get_by_user`) antes de volver a
leerla **con bloqueo** dentro de la transferencia. Cuando una entidad ya está
en el mapa de identidad de la sesión, SQLAlchemy devuelve ese mismo objeto sin
refrescar sus atributos. Resultado: la sentencia `FOR UPDATE` se ejecutaba y el
bloqueo se adquiría, pero la comprobación de fondos usaba el saldo obsoleto
leído antes del bloqueo. Eso es exactamente un lost update.

La corrección es una línea, `execution_options(populate_existing=True)` sobre
la consulta de bloqueo, y está comentada en
`backend/app/modules/accounts/service.py` para que no se pierda el motivo.

Vale la pena dejarlo escrito por tres razones:

1. Ninguna prueba de un solo hilo podía detectarlo. Las 76 pruebas anteriores
   pasaban con el fallo presente.
2. Demuestra que tomar el bloqueo correcto en SQL no basta si la capa de
   mapeo te devuelve datos cacheados.
3. Es la razón por la que las aserciones de este proyecto miran el estado de
   PostgreSQL y no los códigos de respuesta HTTP.

La restricción `CHECK (balance_cents >= 0)` no llegó a dispararse porque el
saldo materializado se calculaba a partir del valor obsoleto y nunca cruzaba
el cero en la fila que se escribía. Es un buen recordatorio de que una
restricción de motor acota el daño pero no sustituye a la prueba.

---

## Prueba D. Cien solicitudes concurrentes

Una cuenta con S/100. Cien hilos, cada uno con su propia conexión, intentan
transferir S/30 a la vez desde una barrera común.

Tres ejecuciones consecutivas de la suite:

| Ejecución | Estrategia | Aprobadas | Rechazadas | Reintentos agotados | Saldo final |
|---|---|---|---|---|---|
| 1 | `pessimistic` | 3 | 97 | 0 | 1000 ctms |
| 1 | `serializable` | 3 | 94 | 3 | 1000 ctms |
| 2 | `pessimistic` | 3 | 97 | 0 | 1000 ctms |
| 2 | `serializable` | 3 | 92 | 5 | 1000 ctms |
| 3 | `pessimistic` | 3 | 97 | 0 | 1000 ctms |
| 3 | `serializable` | 3 | 93 | 4 | 1000 ctms |

Salida literal de la suite:

```
  [pessimistic] resultados de 100 intentos: {'completed': 3, 'rejected': 97}
  [pessimistic] saldo final de Ana: 1000 céntimos
  [serializable] resultados de 100 intentos: {'completed': 3, 'retry_exhausted': 3, 'rejected': 94}
  [serializable] saldo final de Ana: 1000 céntimos
  [pessimistic] resultados de 100 intentos: {'completed': 3, 'rejected': 97}
  [pessimistic] saldo final de Ana: 1000 céntimos
  [serializable] resultados de 100 intentos: {'completed': 3, 'retry_exhausted': 5, 'rejected': 92}
  [serializable] saldo final de Ana: 1000 céntimos
  [pessimistic] resultados de 100 intentos: {'completed': 3, 'rejected': 97}
  [pessimistic] saldo final de Ana: 1000 céntimos
  [serializable] resultados de 100 intentos: {'completed': 3, 'retry_exhausted': 4, 'rejected': 93}
  [serializable] saldo final de Ana: 1000 céntimos
```

### Lectura de los resultados

**Las dos estrategias son correctas.** En las seis ejecuciones se aprueban
exactamente 3 transferencias, el saldo final es 1000 céntimos, ningún saldo
queda negativo y la reconciliación cuadra: la suma global del ledger es cero y
cada saldo materializado coincide con la suma de sus asientos.

**Se diferencian en la calidad del rechazo.** Con bloqueo pesimista, las 97
peticiones que no caben reciben una respuesta de negocio clara: fondos
insuficientes. Con `SERIALIZABLE`, entre 3 y 5 de cada 100 agotan los tres
reintentos ante SQLSTATE 40001 y reciben un 503, que no es una respuesta sobre
su dinero sino sobre el estado del sistema. Bajo la contención máxima de esta
prueba, todas las peticiones compiten por la misma fila, que es el peor caso
para una estrategia optimista.

Esto **confirma la hipótesis declarada en ADR-0005** antes de medir. Las
cifras de throughput y latencia bajo carga sostenida son otra cosa y se
medirán con Locust en la Fase 7.

### Ausencia de deadlocks

Cincuenta transferencias cruzadas simultáneas (25 de Ana a Luis y 25 de Luis a
Ana, el ejemplo de libro de la espera circular) completan las 50 sin un solo
error. `transactional` **no reintenta** ante SQLSTATE 40P01 precisamente para
que un deadlock no quede enmascarado: si el orden de bloqueo fallara, la
prueba se pondría roja.

---

## Prueba E. Fallos

Los tres fallos se provocan de verdad.

### E1. Fallo antes del `COMMIT`

Se inyecta una excepción justo después de escribir los asientos y mover los
saldos, antes de confirmar. Resultado verificado en la base de datos:

- saldos idénticos a los previos
- cero asientos nuevos
- **ninguna** clave de idempotencia registrada
- la respuesta es un 500 que no filtra el mensaje interno del fallo

Y como la clave no llegó a persistirse, el reintento del cliente se procesa
como una petición nueva y la transferencia se ejecuta una vez.

### E2. Fallo después del `COMMIT`, antes de entregar la respuesta

Este es el caso que ninguna propiedad ACID resuelve, porque ocurre fuera del
límite de la transacción. Se rompe la construcción de la respuesta HTTP
después de que la transacción haya confirmado.

- el dinero **sí** se movió: Ana 7000, Luis 3000
- el cliente recibe un 500 y no sabe si pagó
- al reintentar con la misma clave recibe **201 con `Idempotent-Replay: true`**
  y el estado de la base de datos no cambia ni un céntimo

Es exactamente el escenario para el que se diseñó ADR-0006, y funciona porque
la clave se confirma en la misma transacción que el dinero.

Se incluye una contraprueba: dos peticiones idénticas con claves **distintas**
sí mueven el dinero dos veces (Ana 4000, Luis 6000). Deja claro que lo que
evita el duplicado es la clave de idempotencia y no ninguna otra propiedad del
sistema.

### E3. Caída real del proceso de base de datos

No se simula: se obtiene el `pg_backend_pid()` de la transacción en curso y se
mata ese backend desde otra conexión con `pg_terminate_backend`, con los
asientos ya escritos y sin confirmar. Es lo más parecido a un corte de luz que
se puede provocar de forma reproducible.

- el `COMMIT` falla contra una conexión muerta
- el estado de la base de datos es **idéntico** al previo: ni asientos, ni
  saldos movidos, ni transferencia registrada
- la reconciliación sigue cuadrando

Una segunda prueba comprueba que el servicio queda operativo: `pool_pre_ping`
descarta la conexión muerta y la siguiente transferencia se completa con
normalidad.

---

## Suite completa

86 pruebas en verde.

```
$ pytest -v
...
============================= 86 passed in 27.40s ==============================
```
