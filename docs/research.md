# PayCore. Investigación técnica previa al desarrollo (Fase 1)

**Autora:** Manyory Estefany Cueva Mendoza
**Fecha de la investigación:** 18 de octubre de 2026
**Estado del documento:** cerrado para la Fase 1. Las secciones marcadas como *pendiente de medición* se completarán con datos reales en las Fases 6 y 7.

> **Aviso.** PayCore es un prototipo educativo. No se conecta a Yape, a Credicorp, a ninguna entidad bancaria ni a ninguna pasarela de pago. Todo el saldo es ficticio y se expresa en soles peruanos simulados (PEN). No se utilizan marcas, logotipos ni identidades visuales de terceros.

## Cómo leer este documento

Cada subsección sigue la misma estructura: **problema**, **hallazgos verificados**, **alternativas**, **comparación**, **recomendación** y **justificación**. Las fuentes se citan con un identificador corto entre corchetes y se resuelven en la sección 8 con URL, autoría, título y fecha. Cuando una afirmación procede de una medición que todavía no se ha ejecutado, se marca explícitamente como pendiente en lugar de inventar un número.

---

## 1. Integridad transaccional

### 1.1 Problema

El riesgo central de una billetera es que el dinero deje de cuadrar. Dos formas de romperlo:

- **Pérdida de dinero:** se debita al emisor y, por una falla, nunca se acredita al receptor.
- **Creación de dinero:** se acredita al receptor dos veces, o se acredita sin debitar.

Ambos casos producen un sistema en el que la suma de los saldos deja de coincidir con el dinero que debería existir. En un sistema real esto es un incidente contable; en un prototipo es la diferencia entre un proyecto demostrable y una demo vacía.

### 1.2 Hallazgos verificados

**ACID no es un eslogan, es una definición con origen bibliográfico.** El acrónimo se consolida en Haerder y Reuter (1983), *Principles of Transaction-Oriented Database Recovery*, ACM Computing Surveys 15(4), pp. 287-317, DOI 10.1145/289.291 [HR83]. El artículo agrupa atomicidad, consistencia, aislamiento y durabilidad como las propiedades que un gestor transaccional debe garantizar. Citar la fuente original importa porque en entrevistas ACID suele repetirse de memoria sin saber de dónde sale.

Aplicado a PayCore:

| Propiedad | Qué significa aquí | Mecanismo concreto |
|---|---|---|
| Atomicidad | El débito y el crédito ocurren los dos o ninguno | Una sola transacción SQL con `COMMIT`/`ROLLBACK` |
| Consistencia | Ningún saldo negativo, suma de asientos igual a cero | Restricciones `CHECK` y validación de negocio dentro de la transacción |
| Aislamiento | Dos transferencias simultáneas no se pisan | Bloqueo de fila o nivel `SERIALIZABLE` (sección 2) |
| Durabilidad | Una transferencia confirmada sobrevive a un corte | WAL de PostgreSQL |

**Qué pasa si el proceso muere después de debitar y antes de acreditar.** Si ambas operaciones están dentro de la misma transacción y no se ha ejecutado `COMMIT`, no pasa nada: PostgreSQL descarta el trabajo no confirmado. La documentación oficial del WAL explica el mecanismo: los cambios a los ficheros de datos "deben escribirse solo después de que esos cambios se hayan registrado, es decir, después de que los registros WAL que los describen se hayan volcado a almacenamiento permanente", y por eso "en caso de caída podremos recuperar la base de datos usando el log" [PG-WAL]. La consecuencia práctica: la ventana peligrosa no existe *dentro* de la base de datos. Existe *fuera*, entre el `COMMIT` y la respuesta HTTP que el cliente nunca recibe. Ese caso no se resuelve con ACID sino con idempotencia (sección 3).

**Una sola `fsync` confirma muchas transacciones.** La documentación añade que "cuando el servidor procesa muchas transacciones pequeñas concurrentes, un `fsync` del fichero WAL puede bastar para confirmar muchas transacciones" [PG-WAL]. Esto es relevante para la Fase 7: el coste de durabilidad no escala linealmente con las peticiones por segundo.

**Representación del dinero.** PostgreSQL advierte de forma explícita contra el punto flotante para importes: "los números en punto flotante no deberían usarse para manejar dinero debido al potencial de errores de redondeo" [PG-MONEY]. La raíz del problema es que IEEE 754 binario no representa exactamente 0.1 ni 0.01, lo que Goldberg (1991) desarrolla en detalle [GOL91]. Las dos opciones correctas son enteros en unidad mínima (céntimos) o el tipo `numeric` de precisión arbitraria.

**Libro mayor de doble entrada.** Es la práctica contable estándar desde Pacioli (1494), y Fowler la describe como patrón de software: las cuentas son "pots of money" cuyo saldo se deriva de los asientos acumulados, y una transacción contable enlaza explícitamente los asientos entre cuentas [FOW06]. Square documenta haber construido *Books*, un servicio de contabilidad por partida doble inmutable, precisamente porque sus servicios de liquidación "ocasionalmente mostraban inconsistencias de datos que derivaban en consultas de clientes y depósitos retrasados" [SQ19]. Es decir: el ledger no es ornamento académico, es la respuesta de la industria a un problema observado.

**Caso real de fallo con dinero.** El 1 de agosto de 2012 Knight Capital perdió más de 400 millones de dólares en 45 minutos por un despliegue defectuoso. La orden administrativa de la SEC (Release 34-70694, 16 de octubre de 2013) documenta que la firma "no tenía salvaguardas adecuadas para limitar los riesgos" de su acceso al mercado ni revisaba la efectividad de sus controles, y se saldó con una sanción de 12 millones de dólares [SEC13]. El aprendizaje transferible a PayCore no es sobre bases de datos sino sobre controles: las invariantes deben ser verificables de forma independiente al código que las produce, y por eso PayCore incluirá una prueba de reconciliación que recalcula los saldos desde el ledger.

### 1.3 Alternativas evaluadas

**A. Representación del importe**

| Opción | Ventajas | Limitaciones |
|---|---|---|
| `BIGINT` en céntimos | Aritmética exacta y rápida, la invariante "suma de asientos = 0" es exacta por construcción, convención habitual en APIs de pago | No admite fracciones de céntimo (intereses, comisiones prorrateadas), obliga a convertir en la frontera de la API |
| `NUMERIC(18,2)` | Legible en SQL, escala explícita, exacto | Aritmética más lenta que entera, riesgo de deriva de escala si alguna operación produce más decimales, mayor tamaño de almacenamiento |
| `MONEY` de PostgreSQL | Tipo dedicado | Precisión fraccional dependiente de `lc_monetary`, dependiente de configuración regional, poco portable |
| `FLOAT`/`DOUBLE` | Ninguna en este contexto | Descartado por la propia documentación de PostgreSQL [PG-MONEY] y por [GOL91] |

**B. Fuente de verdad del saldo**

| Opción | Ventajas | Limitaciones |
|---|---|---|
| Solo columna `balance` mutable | Lectura O(1), bloqueo trivial | Sin auditoría, un bug sobrescribe el saldo sin dejar rastro, imposible reconstruir el histórico |
| Solo ledger (saldo = `SUM(asientos)`) | Auditable, inmutable, cuadre garantizado | Lectura O(n) y creciente, aplicar "saldo no negativo" de forma atómica exige agregar bajo bloqueo en cada transferencia |
| Ledger como verdad + saldo materializado | Lectura O(1), auditoría completa, fila concreta sobre la que bloquear, `CHECK` de no negatividad a nivel de motor | Dos lugares que deben coincidir, requiere que ambos se escriban en la misma transacción y una rutina de reconciliación |

### 1.4 Recomendación

1. **Importes en `BIGINT` de céntimos** dentro del dominio y la base de datos. Conversión a `Decimal` con dos decimales únicamente en la serialización de entrada y salida de la API. El rango de `BIGINT` cubre holgadamente cualquier escenario del prototipo.
2. **Ledger de doble entrada inmutable (`ledger_entries`) como fuente de verdad**, con `accounts.balance_cents` como proyección materializada escrita en la misma transacción.
3. **Invariantes empujadas al motor**, no solo al código Python:
   - `CHECK (balance_cents >= 0)` sobre `accounts`.
   - `CHECK (amount_cents > 0)` sobre los importes de transferencia.
   - Asientos siempre en pares con signo opuesto y misma magnitud, ligados por `transfer_id`.
   - Ledger de solo inserción: sin `UPDATE` ni `DELETE` en la capa de aplicación, reforzado opcionalmente con un `RULE`/trigger.
4. **Prueba de reconciliación automatizada** que verifica, sobre la base de datos real y no sobre respuestas HTTP:
   - `SUM(ledger_entries.amount_cents) = 0` a nivel global.
   - Para cada cuenta, `SUM(asientos de la cuenta) = accounts.balance_cents`.

### 1.5 Justificación

La combinación ledger inmutable más saldo materializado es la que permite demostrar las tres cosas que un entrevistador va a preguntar: que el dinero no se pierde (reconciliación), que no se puede quedar en negativo (restricción del motor, no del framework) y que existe un rastro de auditoría. El coste es un invariante adicional que mantener, y ese coste se paga con una prueba automatizada que lo verifica en cada ejecución del CI. Es exactamente el razonamiento que Square describe al justificar *Books* [SQ19] y el patrón que Fowler documenta [FOW06], trasladado a una escala que una persona puede implementar y defender.

---

## 2. Concurrencia

### 2.1 Problema

Si dos peticiones leen el mismo saldo antes de que ninguna escriba, ambas pueden concluir que hay fondos suficientes y ambas pueden debitar. El resultado es un saldo negativo o dinero creado de la nada.

**Ejemplo numérico con cuentas ficticias.** Ana tiene S/100. Llegan dos transferencias de S/80 cada una, a Luis y a Rosa, en paralelo:

| t | Petición 1 (a Luis) | Petición 2 (a Rosa) | Saldo en BD |
|---|---|---|---|
| t0 | lee saldo = 10000 ctms | | 10000 |
| t1 | | lee saldo = 10000 ctms | 10000 |
| t2 | valida 10000 >= 8000, OK | | 10000 |
| t3 | | valida 10000 >= 8000, OK | 10000 |
| t4 | escribe 10000 - 8000 = 2000 | | 2000 |
| t5 | | escribe 10000 - 8000 = 2000 | 2000 |

Ana envió S/160 teniendo S/100 y su saldo final es S/20. Se crearon S/60 de la nada. Esto es a la vez una **race condition** (el resultado depende del entrelazado temporal) y un **lost update** (la escritura de la petición 1 se perdió porque la 2 partía de una lectura obsoleta).

### 2.2 Hallazgos verificados

**MVCC y niveles de aislamiento en PostgreSQL.** PostgreSQL implementa internamente tres niveles aunque acepta los cuatro del estándar SQL: "el modo Read Uncommitted de PostgreSQL se comporta como Read Committed. Esta es la única forma sensata de mapear los niveles de aislamiento estándar a la arquitectura de control de concurrencia multiversión de PostgreSQL" [PG-ISO]. Por defecto opera en **Read Committed**, que evita lecturas sucias pero **permite** lecturas no repetibles, fantasmas y anomalías de serialización [PG-ISO]. Es decir: el nivel por defecto **no** protege del escenario anterior por sí solo.

La taxonomía de anomalías y por qué los niveles ANSI son insuficientes está analizada en Berenson, Bernstein, Gray, Melton, O'Neil y O'Neil (1995), *A Critique of ANSI SQL Isolation Levels*, SIGMOD 1995, pp. 1-10, DOI 10.1145/223784.223785 [BER95]. Es la referencia canónica para explicar por qué "snapshot isolation" no equivale a serializable.

**Fallos de serialización y SQLSTATE 40001.** En Repeatable Read, si otra transacción confirma una modificación sobre la fila que estamos actualizando, PostgreSQL aborta con `ERROR: could not serialize access due to concurrent update`, y la documentación indica que "cuando una aplicación recibe este mensaje de error, debería abortar la transacción actual y reintentar la transacción completa desde el principio" [PG-ISO]. En Serializable el error es `could not serialize access due to read/write dependencies among transactions`. La documentación es explícita sobre el requisito operativo: "es importante que un entorno que use esta técnica tenga una forma generalizada de manejar los fallos de serialización (que siempre retornan con un valor SQLSTATE de `40001`)" [PG-ISO]. Añade también que "solo las transacciones que actualizan pueden necesitar reintento; las transacciones de solo lectura nunca tendrán conflictos de serialización" [PG-ISO].

**Coste real de SERIALIZABLE en PostgreSQL.** Ports y Grittner, *Serializable Snapshot Isolation in PostgreSQL*, Proceedings of the VLDB Endowment, Vol. 5, No. 12 (2012), p. 1850 y siguientes [PG-SSI]. El resumen del propio artículo reporta que "nuestro modo serializable tiene un coste de rendimiento de menos del 7% respecto a snapshot isolation, y supera significativamente al bloqueo en dos fases en algunas cargas". En la evaluación del microbenchmark SIBENCH matizan que "rastrear dependencias de lectura tiene una sobrecarga de CPU del 10-20%" y que sus optimizaciones de solo lectura reducen ese coste. Son cifras del artículo, no mediciones de PayCore: las nuestras se tomarán en la Fase 7.

**SELECT FOR UPDATE y deadlocks.** La documentación de bloqueo explícito define que "`FOR UPDATE` hace que las filas recuperadas por la sentencia `SELECT` queden bloqueadas como si fueran a actualizarse. Esto impide que otras transacciones las bloqueen, modifiquen o eliminen hasta que la transacción actual termine" [PG-LOCK]. Sobre deadlocks: "PostgreSQL detecta automáticamente las situaciones de deadlock y las resuelve abortando una de las transacciones involucradas", y sobre la prevención: "la mejor defensa contra los deadlocks es generalmente evitarlos asegurándose de que todas las aplicaciones que usan la base de datos adquieran los bloqueos sobre múltiples objetos en un orden consistente" [PG-LOCK].

**Cómo se produce un deadlock en una billetera.** Ana envía a Luis mientras Luis envía a Ana:

| t | Transacción A (Ana→Luis) | Transacción B (Luis→Ana) |
|---|---|---|
| t0 | `SELECT ... WHERE id=Ana FOR UPDATE` (adquiere) | |
| t1 | | `SELECT ... WHERE id=Luis FOR UPDATE` (adquiere) |
| t2 | `SELECT ... WHERE id=Luis FOR UPDATE` (espera a B) | |
| t3 | | `SELECT ... WHERE id=Ana FOR UPDATE` (espera a A) |

Espera circular. PostgreSQL abortará una de las dos. La solución documentada es ordenar: ambas transacciones bloquean primero la cuenta con el identificador menor y después la mayor, con lo que la espera circular se vuelve imposible.

**Soporte en la capa de acceso a datos.** Verificado empíricamente en este entorno con SQLAlchemy 2.1.5: `Select.with_for_update(*, nowait=False, read=False, of=None, skip_locked=False, key_share=False)` compila a `... FOR UPDATE` con el dialecto PostgreSQL. El nivel de aislamiento se configura con `create_engine(..., isolation_level=...)` o por transacción mediante `session.connection(execution_options={"isolation_level": "SERIALIZABLE"})` [SA-TX].

**Locks de Python no sirven.** Un `threading.Lock` protege un proceso. Con Uvicorn o Gunicorn en varios workers, o con dos réplicas del contenedor, hay varios procesos contra la misma base de datos y el lock no existe entre ellos. La garantía debe vivir donde vive el estado compartido: en PostgreSQL.

### 2.3 Alternativas evaluadas

| Estrategia | Cómo funciona | Ventajas | Limitaciones |
|---|---|---|---|
| **Pesimista: `SELECT FOR UPDATE` en orden determinista**, nivel Read Committed | Se bloquean las filas de las dos cuentas ordenadas por id antes de leer el saldo | Comportamiento predecible, sin reintentos, deadlocks eliminados por el orden, fácil de razonar y de explicar | Serializa las operaciones sobre una misma cuenta caliente, el throughput por cuenta está limitado por la duración de la transacción |
| **Optimista: nivel `SERIALIZABLE` con reintento ante 40001** | PostgreSQL detecta dependencias peligrosas y aborta; la aplicación reintenta | Más concurrencia cuando el conflicto es raro, garantía formal de serializabilidad, sin riesgo de deadlock por orden de bloqueo | Requiere lógica de reintento con backoff, bajo contención alta la tasa de abortos crece, coste de seguimiento de dependencias [PG-SSI] |
| **UPDATE condicional atómico** (`UPDATE ... SET balance = balance - :amt WHERE id = :id AND balance >= :amt`) | La comprobación y la escritura son una sola sentencia | Muy simple, sin lectura previa, el motor garantiza atomicidad de la fila | Encaja peor con un ledger donde hay que insertar asientos y decidir en función del resultado, y mezcla validación con escritura dificultando mensajes de error de negocio |
| **Cola serializada por cuenta** (un consumidor por partición) | Las operaciones de una cuenta se procesan en serie | Elimina la contención por diseño | Exige broker o tabla de cola, latencia añadida, complejidad operativa no justificada en este alcance |
| **Lock de aplicación en Python** | `threading.Lock` o similar | Ninguna aquí | No funciona entre procesos ni entre réplicas. Descartado |

### 2.4 Recomendación

**Implementar las dos primeras estrategias detrás de una opción de configuración y medirlas.**

- **Por defecto, pesimista:** `SELECT ... FOR UPDATE` sobre las dos cuentas, adquiridas siempre en orden ascendente de identificador, dentro de una transacción en Read Committed. Esto resuelve el lost update y el deadlock con mecanismos documentados por PostgreSQL [PG-LOCK].
- **Modo alternativo, optimista:** `SERIALIZABLE` con reintento acotado (por ejemplo, hasta 3 intentos con backoff exponencial y jitter) ante SQLSTATE 40001, siguiendo la indicación explícita de la documentación [PG-ISO].
- **Red de seguridad independiente de la estrategia:** `CHECK (balance_cents >= 0)`. Aunque la lógica falle, el motor rechaza la escritura.

### 2.5 Justificación

Tener las dos estrategias convierte una afirmación de libro en un experimento propio: la Fase 7 compara ambas bajo la misma carga y el informe reporta números medidos, no citados. Es también la respuesta honesta a la pregunta de entrevista "¿por qué elegiste bloqueo pesimista?", porque permite contestar con datos del proyecto en lugar de con una preferencia.

La elección del pesimista como opción por defecto responde al perfil de carga esperado: en la Prueba D, cien peticiones compiten por **la misma** cuenta. Bajo contención máxima el optimista degenera en abortos y reintentos, mientras que el pesimista forma una cola ordenada. Esta hipótesis se contrastará con medición real (*pendiente de medición, Fase 7*).

---

## 3. Idempotencia

### 3.1 Problema

El cliente envía una transferencia. La red se cae **después** de que el servidor haya confirmado la transacción pero **antes** de que la respuesta llegue. El cliente no sabe si el dinero se movió. Si reintenta y el servidor trata la petición como nueva, Ana paga dos veces. Si no reintenta, puede que no haya pagado nunca. Ninguna propiedad ACID resuelve esto, porque el problema está fuera del límite de la transacción.

### 3.2 Hallazgos verificados

**Qué hace Stripe.** La documentación de la API v1 establece que "Stripe guarda el código de estado y el cuerpo de la primera petición hecha con una clave de idempotencia dada después de que comience la ejecución del endpoint. Los reintentos con la misma clave devuelven la respuesta guardada, incluidos los errores `500`" [ST-API]. Sobre la generación de claves: "sugerimos usar UUID v4, u otra cadena aleatoria con suficiente entropía para evitar colisiones. Las claves de idempotencia tienen hasta 255 caracteres. Evite usar datos sensibles (por ejemplo, direcciones de correo o identificadores personales) como claves de idempotencia" [ST-API]. Sobre caducidad: "puede eliminar las claves del sistema automáticamente después de que tengan al menos 24 horas" [ST-API]. Sobre reutilización con parámetros distintos: "la capa de idempotencia compara los parámetros entrantes con los de la petición original y da error si no son los mismos, para prevenir un mal uso accidental" [ST-API]. Y sobre concurrencia: "no guardamos el resultado idempotente si la petición entra en conflicto con otra petición que se está ejecutando concurrentemente" [ST-API], de modo que esas peticiones se pueden reintentar.

El artículo de ingeniería de Brandur Leach (Stripe, 22 de febrero de 2017) desarrolla el razonamiento: implementar los endpoints "de forma que sean idempotentes, lo que significa que pueden llamarse cualquier número de veces garantizando que los efectos secundarios ocurran solo una vez", y recomienda reintentos del cliente con "backoff exponencial y jitter aleatorio" para evitar el problema de la estampida [ST-BLOG].

Se documenta lo que Stripe publica. **No se asume nada sobre la arquitectura interna de Yape**, de la que no existe documentación pública verificable.

**Qué dice el borrador del IETF.** `draft-ietf-httpapi-idempotency-key-header-07` (grupo de trabajo httpapi, revisión del 15 de octubre de 2025, actualmente **expirado**, por lo que se cita como práctica emergente y no como estándar) [IETF-IDEM]:

| Situación | Comportamiento recomendado |
|---|---|
| Clave nueva | "El recurso DEBERÍA procesar la petición normalmente y responder con una respuesta y un código de estado apropiados" |
| Reintento, misma clave y mismo cuerpo | "El recurso DEBERÍA responder con el resultado de la operación completada previamente, éxito o error" |
| Misma clave, cuerpo distinto | HTTP **422 Unprocessable Content** |
| Reintento mientras la original sigue procesándose | HTTP **409 Conflict** |
| Caducidad | "El recurso PUEDE requerir claves de idempotencia basadas en tiempo para poder purgar o eliminar una clave al caducar. El recurso DEBERÍA definir esa política de expiración y publicarla en la documentación" |

### 3.3 Alternativas evaluadas

| Opción | Ventajas | Limitaciones |
|---|---|---|
| **Sin idempotencia**, confiar en que el cliente no reintente | Nada que implementar | Inaceptable. El enunciado de la Prueba C la exige y es un fallo de diseño real |
| **Deduplicación por ventana temporal** (mismo emisor, receptor e importe en N segundos) | No requiere cooperación del cliente | Heurística: rechaza transferencias legítimas repetidas (pagar dos cafés iguales) y no cubre reintentos tardíos. Es una conjetura disfrazada de garantía |
| **Clave de idempotencia en memoria del proceso** | Trivial | Se pierde al reiniciar y no se comparte entre workers ni réplicas. Mismo defecto que el lock de Python |
| **Clave de idempotencia persistida en PostgreSQL, en la misma transacción que la transferencia** | Sobrevive a reinicios, funciona entre procesos, sin ventana entre mover dinero y registrar la clave | Requiere una tabla, una política de purga y manejar el estado "en curso" |
| **Clave persistida en Redis** | Rápido, TTL nativo | Añade un componente de infraestructura y, sobre todo, rompe la atomicidad: la clave y el movimiento de dinero quedan en sistemas distintos, lo que reintroduce exactamente la ventana que queríamos cerrar. Descartado por la regla de no añadir dependencias sin justificación |

### 3.4 Recomendación

Tabla `idempotency_keys` en PostgreSQL con:

- `UNIQUE (user_id, key)`. El ámbito es **por usuario autenticado**, no global. Esto evita colisiones entre clientes y, más importante, impide que un usuario pueda sondear o secuestrar la respuesta de otro reutilizando una clave ajena. Es una propiedad de seguridad además de una de corrección.
- `request_fingerprint`: hash SHA-256 del método, la ruta y el cuerpo canonicalizado, para detectar reutilización con parámetros distintos.
- `state`: `in_progress` | `succeeded` | `failed`.
- `response_status`, `response_body`, `transfer_id`, `created_at`, `expires_at`.

Protocolo:

1. `INSERT ... ON CONFLICT DO NOTHING` para reclamar la clave de forma atómica. Quien inserta, procesa.
2. Si se reclamó: ejecutar la transferencia y escribir la respuesta en la misma transacción. Un único `COMMIT` cubre los asientos, los saldos y el registro de la clave.
3. Si no se reclamó, leer la fila existente:
   - huella igual y estado `succeeded` o `failed` → responder la respuesta almacenada con cabecera `Idempotent-Replay: true`;
   - huella igual y estado `in_progress` → **409 Conflict** [IETF-IDEM];
   - huella distinta → **422 Unprocessable Content** [IETF-IDEM].
4. TTL de 24 horas, alineado con la práctica publicada de Stripe [ST-API], con purga documentada y ejecutable.

La clave la genera el cliente como UUID v4 y se envía en la cabecera `Idempotency-Key`. Es obligatoria en `POST /transfers`.

### 3.5 Justificación

Escribir la clave y el dinero en la misma transacción es la decisión que hace que esto funcione. Si la clave se guardara después del `COMMIT` del dinero, una caída entre ambos pasos dejaría una transferencia ejecutada sin registro de idempotencia, y el reintento la duplicaría. Al compartir transacción, la atomicidad de PostgreSQL cubre las dos cosas: o se movió el dinero y la clave quedó registrada, o no ocurrió ninguna de las dos. Esto es verificable con la Prueba E y es la respuesta directa a "¿qué pasa si falla la red?".

El uso del estado `in_progress` con respuesta 409 es lo que distingue este diseño de una tabla de deduplicación simple: cubre el caso de dos peticiones **simultáneas** con la misma clave, no solo el de dos peticiones secuenciales.

---

## 4. Arquitectura de software

### 4.1 Problema

Elegir la organización del código que permita construir, probar y explicar el sistema con una sola desarrolladora, sin pagar complejidad operativa que no compra nada.

### 4.2 Hallazgos verificados

Fowler (*MonolithFirst*, 3 de junio de 2015) sostiene que "no deberías empezar un nuevo proyecto con microservicios, incluso si estás seguro de que tu aplicación será lo bastante grande" [FOW15]. Sus dos argumentos son YAGNI y, sobre todo, que establecer fronteras de servicio correctas es difícil sin patrones de uso reales, mientras que un monolito permite descubrir esas fronteras antes de que las restricciones arquitectónicas hagan prohibitivo refactorizar.

Aplicado a PayCore hay un argumento adicional y más fuerte: **la transferencia es atómica**. En un monolito con una base de datos, la atomicidad es un `COMMIT`. Si se separan "cuentas" y "ledger" en servicios con bases de datos distintas, la atomicidad desaparece y hay que reintroducirla con Saga o con un commit en dos fases, lo que supone compensaciones, estados intermedios visibles y mucha más superficie de error. Partir el sistema aquí no es una mejora: es cambiar una garantía fuerte y gratuita por una débil y cara.

### 4.3 Comparación

| Arquitectura | Encaje con PayCore | Coste | Veredicto |
|---|---|---|---|
| **Monolito tradicional** (capas, sin fronteras internas) | Funciona y es rápido de escribir | Tiende a acoplarse: la lógica de transferencia se mezcla con HTTP y con el ORM | Insuficiente. No demuestra criterio de diseño |
| **Monolito modular** (módulos con interfaz explícita, una BD, un despliegue) | La atomicidad sigue siendo un `COMMIT`. Los módulos se prueban por separado. Las fronteras quedan documentadas | Disciplina para no saltarse las fronteras | **Recomendado** |
| **Microservicios** | Rompe la atomicidad de la transferencia. Exige Saga o 2PC | Red, descubrimiento, observabilidad distribuida, despliegue múltiple, pruebas de integración complejas | Descartado para el MVP [FOW15] |
| **Orientada a eventos** | Útil para lo que *sigue* a la transferencia (notificaciones, antifraude, analítica) | Broker, entrega al menos una vez, consumidores idempotentes, orden | Descartado como núcleo. Se documenta como vía de evolución y se deja el ledger preparado para servir de log de eventos |
| **Hexagonal / puertos y adaptadores** | Aporta de forma demostrable: permite probar la lógica de transferencia sin HTTP, y aislar el repositorio de cuentas | Algo de indirección | **Adoptada parcialmente**, solo donde se paga sola: el dominio no importa FastAPI ni SQLAlchemy |

### 4.4 Recomendación

**Monolito modular con el núcleo de dominio aislado al estilo hexagonal.** Módulos previstos:

```
backend/app/
  modules/
    identity/     registro, autenticación, hashing de contraseñas
    accounts/     cuentas, consulta de saldo
    ledger/       asientos de doble entrada, reconciliación
    transfers/    caso de uso de transferencia, estrategias de concurrencia
    idempotency/  reclamación de claves, reproducción de respuestas
  platform/       config, BD, errores, logging, seguridad, rate limiting
  api/            routers FastAPI, esquemas Pydantic, dependencias
```

Regla de frontera explícita: un módulo no accede a las tablas de otro. `transfers` orquesta `accounts`, `ledger` e `idempotency` a través de sus servicios, dentro de una única transacción de base de datos gestionada por una unidad de trabajo.

### 4.5 Justificación

Es la opción que maximiza lo que el proyecto puede demostrar por unidad de complejidad. Mantiene intacta la garantía que da valor al proyecto (atomicidad real), permite escribir pruebas de dominio sin levantar HTTP, y deja documentado el camino a microservicios o a eventos como trabajo futuro justificado en lugar de como decoración.

---

## 5. Seguridad

### 5.1 Problema

Un prototipo de billetera que no controla quién puede mover el dinero de quién no demuestra nada. La superficie de riesgo relevante aquí es de API, no de red ni de infraestructura.

### 5.2 Hallazgos verificados

**OWASP API Security Top 10 (edición 2023)** [OWASP-API]:

| Código | Título |
|---|---|
| API1:2023 | Broken Object Level Authorization |
| API2:2023 | Broken Authentication |
| API3:2023 | Broken Object Property Level Authorization |
| API4:2023 | Unrestricted Resource Consumption |
| API5:2023 | Broken Function Level Authorization |
| API6:2023 | Unrestricted Access to Sensitive Business Flows |
| API7:2023 | Server Side Request Forgery |
| API8:2023 | Security Misconfiguration |
| API9:2023 | Improper Inventory Management |
| API10:2023 | Unsafe Consumption of APIs |

El primero de la lista es exactamente el riesgo de PayCore: que Ana pueda transferir desde la cuenta de Luis pasando el identificador de Luis en el cuerpo de la petición. La Prueba F lo verifica.

**Almacenamiento de contraseñas.** OWASP recomienda como primera opción "usar Argon2id con una configuración mínima de 19 MiB de memoria, un recuento de iteraciones de 2 y 1 grado de paralelismo" [OWASP-PWD]. La hoja ofrece configuraciones mínimas equivalentes (m=19456/t=2/p=1, m=47104/t=1/p=1, m=12288/t=3/p=1, m=9216/t=4/p=1, m=7168/t=5/p=1). Para bcrypt, en sistemas heredados, "el factor de trabajo debería ser tan grande como el rendimiento del servidor de verificación permita, con un mínimo de 10", y advierte de que "bcrypt tiene una longitud máxima de entrada de 72 bytes" [OWASP-PWD].

### 5.3 Recomendación por riesgo

| Riesgo OWASP | Cómo se mitiga en PayCore | Cómo se verifica |
|---|---|---|
| API1 Broken Object Level Authorization | La cuenta origen **nunca** se toma del cuerpo de la petición: se deriva del sujeto del token. Toda consulta de cuenta o de historial filtra por el propietario autenticado | Prueba F automatizada: Ana pide `GET /accounts/{id_de_Luis}` y recibe 404 |
| API2 Broken Authentication | Argon2id con los parámetros mínimos de OWASP, JWT de vida corta firmado con secreto de entorno, sin credenciales por defecto en el repositorio | Pruebas de token expirado, firma inválida y ausencia de cabecera |
| API3 Broken Object Property Level | Esquemas Pydantic explícitos de entrada y de salida. El `balance_cents` nunca se acepta desde el cliente; los hashes nunca se serializan | Prueba de que un `POST` con campos extra no los persiste |
| API4 Unrestricted Resource Consumption | Rate limiting por usuario y por IP en los endpoints de login y de transferencia, paginación obligatoria en el historial, límite de tamaño de cuerpo | Prueba que satura el límite y espera 429 |
| API5 Broken Function Level | Dependencia de autenticación aplicada a nivel de router, no endpoint por endpoint, para que olvidarla sea difícil | Prueba que recorre la especificación OpenAPI y verifica que todo endpoint no público exige token |
| API6 Sensitive Business Flows | La transferencia exige `Idempotency-Key` y está sujeta a rate limit | Prueba C y prueba de rate limit |
| API7 SSRF | PayCore no hace peticiones salientes a URLs proporcionadas por el usuario. Riesgo no aplicable, se documenta como tal | Revisión de código |
| API8 Security Misconfiguration | `.env.example` sin secretos reales, CORS restringido, errores sin traza interna hacia el cliente, dependencias versionadas | Revisión manual y escaneo de dependencias en CI |
| API9 Improper Inventory Management | OpenAPI generada automáticamente por FastAPI y versionada en el repositorio, prefijo `/api/v1` | Diff de OpenAPI en CI |
| API10 Unsafe Consumption of APIs | PayCore no consume APIs de terceros | Documentado como no aplicable |

**Validación de entradas.** Toda entrada pasa por Pydantic. Reglas específicas de dinero: importe entero positivo, mayor que cero, con tope máximo por operación; emisor distinto de receptor; moneda fija a PEN simulado. El uso del ORM con parámetros vinculados elimina la inyección SQL por construcción; no se construirá SQL por concatenación de cadenas.

**Gestión de secretos.** Variables de entorno, `.env` en `.gitignore`, `.env.example` con valores obviamente falsos, secreto JWT generado en el arranque de desarrollo y obligatorio en producción. En CI, secretos de GitHub Actions.

**Logs.** Logging estructurado en JSON con identificador de correlación por petición. Lista de denegación explícita: nunca se registran contraseñas, tokens, cabeceras `Authorization` ni claves de idempotencia completas. Los importes y los identificadores de cuenta sí se registran, porque son datos ficticios y hacen falta para auditar.

### 5.4 Justificación

Se ordena el trabajo de seguridad por el Top 10 de OWASP porque es el marco de referencia que un entrevistador de banca reconoce, y porque convierte "el proyecto es seguro" en una tabla con una prueba por fila. Argon2id con parámetros citados textualmente de OWASP es preferible a elegir un coste arbitrario, y permite responder la pregunta "¿por qué esos parámetros?" con una fuente.

---

## 6. IA y tecnologías avanzadas

### 6.1 Problema

Decidir si alguna técnica de aprendizaje automático o de modelos fundacionales resuelve un problema real de PayCore, o si solo añadiría vistosidad.

### 6.2 Criterio

Sculley et al., *Hidden Technical Debt in Machine Learning Systems*, NIPS 2015, pp. 2503-2511 [SCU15], argumentan que los sistemas de ML reales incurren en costes de mantenimiento continuos y masivos: el código de modelo es una fracción pequeña del sistema, y el resto (datos, validación, monitorización, configuración) es deuda. Para un proyecto de portafolio, añadir ML sin datos reales y sin evaluación produce exactamente esa deuda sin ninguno de los beneficios.

### 6.3 Evaluación por técnica

| Técnica | Qué problema resolvería | Datos que necesita | Cómo se evaluaría | Veredicto |
|---|---|---|---|---|
| **Reglas de riesgo deterministas** (velocidad de envío, importe atípico frente al histórico propio, receptor nuevo) | Marcar operaciones sospechosas para revisión | Solo el historial del propio sistema | Precisión y cobertura sobre un conjunto etiquetado a mano con datos sintéticos | **Fase 2, recomendado.** Barato, explicable, auditable, y es lo que un sistema real pone primero |
| **Detección de anomalías no supervisada** (Isolation Forest, autoencoder) | Detectar patrones no previstos por las reglas | Volumen suficiente de transacciones con distribución realista | Curva precisión/cobertura contra etiquetas sintéticas; comparación contra la línea base de reglas | **Fase 2, opcional.** Honesto solo si se declara que los datos son sintéticos y que el resultado no es generalizable |
| **Clasificador supervisado de fraude** | Puntuar riesgo | Transacciones reales etiquetadas como fraude. **No existen y no se pueden fabricar sin falsear el resultado** | No evaluable de forma creíble | Descartado |
| **Modelos fundacionales / LLM** | Interfaz en lenguaje natural, resúmenes de gasto | Ninguno adicional | Evaluación cualitativa | Descartado del MVP. Útil como explicador del historial en una fase posterior, nunca en la ruta de decisión |
| **RAG + base de datos vectorial** | Preguntas sobre documentación o normativa | Corpus documental, que PayCore no tiene | No aplicable | Descartado. Sería infraestructura sin problema que resolver |

### 6.4 Recomendación y límite duro

**El MVP no incluye IA.** Se planifica para una Fase 2 un servicio de riesgo basado en reglas, con la detección de anomalías no supervisada como experimento opcional y claramente etiquetado.

**Límite de diseño, no negociable:** ningún modelo generativo ni estadístico aprueba, rechaza ni modifica una transferencia o un saldo. El motor de riesgo solo puede producir una **marca de revisión** adjunta a la operación. La decisión sobre el dinero la toman las reglas de negocio deterministas y las restricciones de la base de datos. Un sistema no determinista no puede estar en la ruta crítica del dinero, y poder explicar por qué es más valioso en una entrevista que haber conectado un modelo.

---

## 7. Síntesis de recomendaciones de la Fase 1

| # | Decisión | ADR |
|---|---|---|
| 1 | Monolito modular con dominio aislado, una base de datos, un despliegue | ADR-0001 |
| 2 | PostgreSQL como motor | ADR-0002 |
| 3 | Importes en `BIGINT` de céntimos | ADR-0003 |
| 4 | Ledger de doble entrada como fuente de verdad, saldo materializado | ADR-0004 |
| 5 | Concurrencia pesimista por defecto con orden determinista de bloqueo, modo `SERIALIZABLE` con reintento como alternativa medible | ADR-0005 |
| 6 | Idempotencia persistida en la misma transacción, ámbito por usuario, 409/422 según el borrador del IETF | ADR-0006 |
| 7 | Autenticación JWT con Argon2id según parámetros de OWASP | ADR-0007 |
| 8 | Sin IA en el MVP, límite duro de no decisión automática sobre el dinero | ADR-0008 |

---

## 8. Fuentes

Todas las fuentes se consultaron el 18 de octubre de 2026.

| Id | Referencia |
|---|---|
| [HR83] | Haerder, T. y Reuter, A. (diciembre de 1983). *Principles of Transaction-Oriented Database Recovery*. ACM Computing Surveys, 15(4), 287-317. DOI 10.1145/289.291. https://dl.acm.org/doi/10.1145/289.291 |
| [BER95] | Berenson, H., Bernstein, P., Gray, J., Melton, J., O'Neil, E. y O'Neil, P. (1995). *A Critique of ANSI SQL Isolation Levels*. Proceedings of the 1995 ACM SIGMOD International Conference on Management of Data, 1-10. DOI 10.1145/223784.223785. https://dl.acm.org/doi/10.1145/568271.223785 |
| [PG-SSI] | Ports, D. R. K. y Grittner, K. (2012). *Serializable Snapshot Isolation in PostgreSQL*. Proceedings of the VLDB Endowment, 5(12). https://www.vldb.org/pvldb/vol5/p1850_danrkports_vldb2012.pdf |
| [GOL91] | Goldberg, D. (marzo de 1991). *What Every Computer Scientist Should Know About Floating-Point Arithmetic*. ACM Computing Surveys, 23(1), 5-48. DOI 10.1145/103162.103163. https://dl.acm.org/doi/10.1145/103162.103163 |
| [SCU15] | Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D., Chaudhary, V., Young, M., Crespo, J.-F. y Dennison, D. (2015). *Hidden Technical Debt in Machine Learning Systems*. Advances in Neural Information Processing Systems 28 (NIPS 2015), 2503-2511. https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems |
| [PG-ISO] | PostgreSQL Global Development Group. *PostgreSQL 16 Documentation, 13.2. Transaction Isolation*. https://www.postgresql.org/docs/16/transaction-iso.html |
| [PG-LOCK] | PostgreSQL Global Development Group. *PostgreSQL 16 Documentation, 13.3. Explicit Locking*. https://www.postgresql.org/docs/16/explicit-locking.html |
| [PG-WAL] | PostgreSQL Global Development Group. *PostgreSQL 16 Documentation, 29.3. Write-Ahead Logging (WAL)*. https://www.postgresql.org/docs/16/wal-intro.html |
| [PG-MONEY] | PostgreSQL Global Development Group. *PostgreSQL 16 Documentation, 8.2. Monetary Types*. https://www.postgresql.org/docs/16/datatype-money.html |
| [ST-API] | Stripe. *API Reference, Idempotent requests*. https://docs.stripe.com/api/idempotent_requests |
| [ST-BLOG] | Leach, B. (22 de febrero de 2017). *Designing robust and predictable APIs with idempotency*. Stripe Blog. https://stripe.com/blog/idempotency |
| [IETF-IDEM] | Jena, J. y otros. *The Idempotency-Key HTTP Header Field*, draft-ietf-httpapi-idempotency-key-header-07, IETF HTTPAPI Working Group, 15 de octubre de 2025. Estado: expirado. https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/ |
| [OWASP-API] | OWASP. *API Security Top 10, edición 2023*. https://owasp.org/API-Security/editions/2023/en/0x11-t10/ |
| [OWASP-PWD] | OWASP. *Password Storage Cheat Sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html |
| [FOW15] | Fowler, M. (3 de junio de 2015). *MonolithFirst*. https://martinfowler.com/bliki/MonolithFirst.html |
| [FOW06] | Fowler, M. (24 de enero de 2006). *Accounting Narrative* (patrones de contabilidad). https://martinfowler.com/eaaDev/AccountingNarrative.html |
| [SQ19] | Square (16 de octubre de 2019). *Books, an immutable double-entry accounting database service*. Square Developer Blog. https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/ |
| [SEC13] | U.S. Securities and Exchange Commission (16 de octubre de 2013). *In the Matter of Knight Capital Americas LLC*, Release No. 34-70694, File No. 3-15570. https://www.sec.gov/files/litigation/admin/2013/34-70694.pdf |
| [DEAN13] | Dean, J. y Barroso, L. A. (febrero de 2013). *The Tail at Scale*. Communications of the ACM, 56(2), 74-80. DOI 10.1145/2408776.2408794. https://cacm.acm.org/research/the-tail-at-scale/ |
| [SA-TX] | SQLAlchemy. *Transactions and Connection Management (ORM), SQLAlchemy 2.0 Documentation*. https://docs.sqlalchemy.org/en/20/orm/session_transaction.html |
| [LOCUST] | Locust. *What is Locust?*. https://docs.locust.io/en/stable/what-is-locust.html |
| [FASTAPI] | Ramírez, S. *FastAPI Documentation*. https://fastapi.tiangolo.com/ |
| [ALEMBIC] | Bayer, M. *Alembic Documentation*. https://alembic.sqlalchemy.org/en/latest/ |

### Verificaciones empíricas hechas en este entorno

No son fuentes bibliográficas, son comprobaciones ejecutadas localmente el 18 de octubre de 2026 y reproducibles:

- SQLAlchemy 2.1.5: `Select.with_for_update(*, nowait=False, read=False, of=None, skip_locked=False, key_share=False)` compila a `SELECT ... FOR UPDATE` con el dialecto PostgreSQL.
- Entorno de desarrollo disponible: Python 3.12.3, Docker 29.4.0, Docker Compose v5.1.2, cliente `psql` 16.15, Node v20.19.6, `pdflatex` y `latexmk` de TeX Live con `tikz`, `biblatex` y `booktabs` presentes. `biber` **no** está instalado, lo que condiciona el backend bibliográfico de la Fase 8.
