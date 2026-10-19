# PayCore. Preparación para la entrevista técnica

Todas las respuestas se refieren a decisiones y código **realmente implementados**. Cuando algo no está hecho, lo dice.

Regla antes de empezar: si en la entrevista te preguntan algo que no hiciste, la respuesta correcta es «eso no lo implementé, y la razón es esta». Nunca inventes. El proyecto está construido precisamente para que no haga falta.

---

## Parte 1. Las tres formas de contarlo

### 30 segundos, para Recursos Humanos

> PayCore es una billetera digital simulada que construí para demostrar cómo se garantiza que el dinero no se pierda ni se duplique en un sistema de pagos. Son transferencias entre cuentas ficticias, con libro contable de doble entrada, y lo probé con cien peticiones simultáneas sobre la misma cuenta para comprobar que los saldos cuadran siempre. Está en Python con FastAPI y PostgreSQL, con interfaz en React, y todo el código y las mediciones están en GitHub.

Si te preguntan «¿es como Yape?»: *«No, no está conectado a nada real ni copia su diseño. Lo hice para practicar la parte de ingeniería que hay detrás de cualquier billetera: que una transferencia sea atómica y que no se pueda cobrar dos veces.»*

### 2 minutos, técnica

> El problema de una billetera no es restar y sumar, es qué pasa cuando eso sale mal. PayCore ataca cuatro escenarios: que el proceso muera a mitad de la operación, que dos peticiones lleguen a la vez, que la respuesta se pierda y el cliente reintente, y que alguien intente operar sobre una cuenta ajena.
>
> Para el primero, una transferencia es una sola transacción: o se escriben los dos asientos y los dos saldos, o ninguno. Para el segundo, bloqueo las dos filas de cuenta con `SELECT FOR UPDATE` en orden ascendente de identificador, lo que elimina los deadlocks; además implementé la alternativa con `SERIALIZABLE` y reintentos para poder compararlas con datos propios. Para el tercero, la clave de idempotencia se escribe en la **misma transacción** que el dinero, así que no hay ningún instante en el que el saldo haya cambiado y la clave no esté registrada. Para el cuarto, la cuenta de origen sale siempre del token, nunca del cuerpo de la petición.
>
> Lo que más me enseñó el proyecto fueron dos fallos que encontraron las pruebas. La de concurrencia destapó un *lost update*: el bloqueo se tomaba bien, pero el mapa de identidad de SQLAlchemy me devolvía el objeto con el saldo viejo, así que aprobaba 88 transferencias de 100 cuando el máximo eran 3. Y la prueba de carga destapó que el pool de conexiones se agotaba porque la sesión se abría como dependencia del framework y la conexión quedaba retenida fuera del hilo que la usaba; arreglarlo multiplicó por 7,4 el rendimiento de lectura.

### Profunda, con ingenieros

Ahí ya no hay guion. Lleva a mano estos cuatro puntos de entrada:

1. **El ledger como fuente de verdad** y por qué el saldo materializado necesita una prueba de reconciliación que lo recalcule.
2. **Por qué dos sentencias de bloqueo y no un `IN (...) ORDER BY`**: el orden de bloqueo de un conjunto depende del plan.
3. **Por qué la idempotencia no puede ir en Redis**: rompería la atomicidad que es justo lo que resuelve.
4. **Medir la API no es verificar el dinero**: 63,1 req/s frente a 10,4 transferencias realmente confirmadas por segundo.

---

## Parte 2. Preguntas y respuestas

### ¿Por qué PostgreSQL?

Porque necesitaba tres cosas a la vez y es el único candidato que evalué que las tiene todas: `SELECT FOR UPDATE` con semántica documentada, un `SERIALIZABLE` de verdad implementado con *serializable snapshot isolation*, y restricciones `CHECK` de columna.

Ese tercer punto es el que más me importaba: quería que «ningún saldo negativo» fuera una garantía del motor y no una promesa de mi código Python. Tengo 17 pruebas que atacan las invariantes con SQL directo, sin pasar por la aplicación.

Descarté MySQL porque su `SERIALIZABLE` se apoya en bloqueo, así que comparar las dos estrategias habría sido comparar motores. Y SQLite porque su concurrencia de escritura es a nivel de fichero: la prueba de los cien hilos dejaría de medir lo que pretende.

### ¿Qué significa ACID?

Atomicidad, consistencia, aislamiento y durabilidad. El acrónimo viene de Haerder y Reuter, 1983, en ACM Computing Surveys.

Traducido a PayCore: atomicidad es que el débito y el crédito van en la misma transacción; consistencia son los `CHECK` y el trigger que verifica que los asientos suman cero; aislamiento es el bloqueo ordenado o el nivel serializable; durabilidad es el WAL de PostgreSQL.

**Lo que suelo añadir, porque es lo que de verdad entendí haciendo el proyecto:** ACID no resuelve el problema de la respuesta perdida. Si el `COMMIT` ya ocurrió y la red se cae antes de que el cliente reciba la respuesta, ninguna de las cuatro propiedades te ayuda, porque el problema está fuera del límite de la transacción. Eso se resuelve con idempotencia.

### ¿Cómo evitaste las condiciones de carrera?

Con bloqueo pesimista a nivel de fila: `SELECT ... FOR UPDATE` sobre las dos cuentas, dentro de la transacción.

El detalle que importa es el **orden**. Si Ana envía a Luis mientras Luis envía a Ana y cada transacción bloquea en el orden en que le conviene, tienes una espera circular. Yo las bloqueo siempre en orden ascendente de identificador, con lo que el deadlock se vuelve imposible.

Y hay un matiz: **no uso `WHERE id IN (:a, :b) ORDER BY id FOR UPDATE`**, que es la formulación que uno escribiría primero. El orden en que PostgreSQL adquiere los bloqueos de un conjunto depende del plan de ejecución, no de la cláusula de ordenación. Emito dos sentencias separadas, así el orden lo impone la aplicación.

Tengo una prueba con 50 transferencias cruzadas simultáneas que exige que las 50 se completen sin un solo error. Y el deadlock, SQLSTATE 40P01, **no se reintenta a propósito**: si el orden fallara, quiero que la prueba se ponga roja en vez de que el reintento lo esconda.

### ¿Qué diferencia hay entre concurrencia y paralelismo?

Concurrencia es que varias tareas estén en curso durante el mismo intervalo; paralelismo es que se ejecuten literalmente a la vez en varios núcleos.

En PayCore se ven las dos. Concurrencia: un proceso de API atiende muchas peticiones intercaladas. Paralelismo: lo corrí con cuatro workers de Uvicorn, así que hay cuatro procesos del sistema operativo ejecutándose de verdad en paralelo contra la misma base.

Eso es justamente por lo que **un `threading.Lock` de Python no sirve**: protege un proceso. Con cuatro, el lock no existe entre ellos. La garantía tiene que vivir donde vive el estado compartido, que es PostgreSQL.

### ¿Por qué no microservicios desde el principio?

Porque la transferencia tiene que ser atómica. En un monolito con una base de datos, la atomicidad es un `COMMIT`. Si separo cuentas y ledger en servicios con bases distintas, la atomicidad desaparece y tengo que reintroducirla con Saga o un commit en dos fases: compensaciones, estados intermedios visibles y mucha más superficie de error.

Estaría cambiando una garantía fuerte y gratuita por una débil y cara, a cambio de una escalabilidad que este sistema no necesita.

Fowler lo argumenta en *MonolithFirst*: cuesta acertar con las fronteras de servicio sin patrones de uso reales. Lo que sí hice fue un monolito **modular**, con la regla de que ningún módulo toca las tablas de otro. Esas fronteras son el mapa de una extracción futura si hiciera falta.

### ¿Cómo funciona la idempotencia?

El cliente genera un UUID v4 y lo manda en la cabecera `Idempotency-Key`. En el servidor:

1. `INSERT ... ON CONFLICT DO NOTHING` reclama la clave de forma atómica. Quien inserta, procesa.
2. Si se reclamó, la transferencia y la respuesta se escriben en **la misma transacción**.
3. Si no se reclamó: misma huella y estado finalizado, reproduzco la respuesta guardada con la cabecera `Idempotent-Replay: true`; misma huella y en curso, 409; huella distinta, 422.

Los códigos 409 y 422 salen del borrador del IETF sobre esa cabecera, que está expirado y por eso lo cito como práctica emergente y no como estándar. El TTL de 24 horas está alineado con lo que Stripe publica.

**Lo que hace que funcione** es que la clave se confirme junto con el dinero. Si la escribiera después del `COMMIT`, una caída entre ambos pasos dejaría una transferencia ejecutada sin registro, y el reintento la duplicaría.

El ámbito es `(user_id, key)` y no solo `key`. Además de evitar colisiones, impide que alguien reutilice la clave de otro para leer su respuesta almacenada. Es una propiedad de seguridad, no solo de corrección.

### ¿Qué ocurre ante una falla de red?

Depende de cuándo:

- **Antes del `COMMIT`:** PostgreSQL deshace todo. Ni asientos, ni saldos movidos, ni clave registrada. El reintento se procesa limpio. Lo compruebo inyectando una excepción justo antes de confirmar.
- **Después del `COMMIT`, antes de responder:** el dinero sí se movió y el cliente recibe un error. Al reintentar con la misma clave obtiene 201 con `Idempotent-Replay: true` y no se mueve nada más. Lo compruebo rompiendo la construcción de la respuesta.
- **Caída del motor a mitad:** esta no la simulo. Obtengo el `pg_backend_pid()` de la transacción y lo mato desde otra conexión con `pg_terminate_backend`, con los asientos ya escritos. El `COMMIT` falla y el estado queda idéntico al previo.

Tengo además una **contraprueba**: dos peticiones idénticas con claves **distintas** sí duplican. Sirve para dejar claro que lo que evita el duplicado es la clave y no otra propiedad del sistema.

Y en el cliente: la interfaz conserva la clave entre reintentos. Si la petición falla por red, muestra «Resultado no confirmado» y reenvía la misma. De poco sirve un servidor idempotente si el cliente genera una clave nueva cada vez.

### ¿Cómo garantizas que no se pierda saldo simulado?

Tres capas, y la tercera es la que de verdad me convence:

1. **Atomicidad.** Los dos asientos y los dos saldos van en la misma transacción.
2. **Restricciones del motor.** `CHECK (balance_cents >= 0)` y un trigger de restricción diferido que, al `COMMIT`, rechaza cualquier transferencia cuyos asientos no sean exactamente dos y no sumen cero.
3. **Reconciliación independiente.** Una comprobación que recalcula cada saldo desde el ledger y lo compara con la columna materializada, y que verifica que la suma global de asientos es cero. Se ejecuta al final de cada suite y después de cada carrera de carga.

La tercera es la importante porque **no confía en el código que produjo los datos**. Es la lección que saqué del caso de Knight Capital: los controles tienen que ser verificables de forma independiente.

El dinero inicial tampoco aparece de la nada: entra desde una cuenta de sistema que sí puede quedar en negativo, así que la suma global sigue siendo exactamente cero y el origen queda auditado.

### ¿Qué pruebas realizaste?

96 automatizadas, contra un PostgreSQL real, no SQLite: lo que verifico son garantías del motor que otro no reproduce.

| Tipo | Cuántas | Qué cubren |
|---|---|---|
| Esquema | 17 | Atacan cada invariante con SQL directo, sin pasar por la aplicación |
| Seguridad | 19 | Ordenadas por riesgo del OWASP API Top 10 2023 |
| Identidad | 13 | Registro, login, hashing, tokens |
| Idempotencia | 10 | Incluida una concurrente con dos hilos |
| Transferencias | 10 | Pruebas A y B, historial, conservación del total |
| Rate limiting | 10 | Cubo de fichas con reloj inyectado, y los endpoints |
| Concurrencia | 5 | Prueba D con las dos estrategias, y deadlocks |
| Fallos | 5 | Prueba E, los tres fallos provocados de verdad |
| Salud y migraciones | 7 | Arranque, correlación, reversibilidad del esquema |

**El principio que las gobierna:** las aserciones sobre dinero consultan PostgreSQL, no las respuestas HTTP. Un servicio que devolviera 201 a todo sin escribir nada pasaría cualquier prueba que solo mire códigos de estado.

### ¿Qué limitaciones reconoces?

Las tengo escritas en el README y en una sección entera del informe. Las que más pesan:

- **Un solo nodo de base de datos.** Punto único de fallo, sin replicación.
- **El rate limiting cuenta en memoria del proceso.** Con cuatro workers, la ráfaga efectiva es cuatro veces la configurada. Está declarado en el código y en el ADR, no escondido.
- **JWT sin revocación inmediata.** Un token robado vale 15 minutos.
- **El token del navegador vive en `sessionStorage`**, legible por un XSS. Lo correcto en producción es una cookie `httpOnly` con protección CSRF.
- **De las mediciones:** cliente y servidor en la misma máquina, omisión coordinada del generador de bucle cerrado, una sola repetición por combinación y sin medición de recursos.

Y una que me parece importante contar: **descarté una de mis propias mediciones** porque no era válida. La carrera del «antes» de una comparación había durado 34 segundos en vez de 60, porque el generador abortaba al fallar un login. Lo detecté revisando las marcas de tiempo, corregí el generador y repetí.

### ¿Cómo escalarías el sistema?

Por orden, y midiendo antes de cada paso:

1. **Vertical primero.** Los datos actuales no muestran que la base sea el cuello de botella a esta carga. Subir recursos es lo más barato.
2. **Réplica de lectura** para saldo e historial, que no necesitan la primaria. Antes habría que confirmar con medición que la lectura molesta; hoy no lo hace.
3. **Más procesos de API.** En cuanto pase de uno, el contador de rate limiting deja de significar lo que dice y hay que compartirlo. Esa es la condición escrita bajo la que entraría Redis.
4. **Particionado por cuenta** si apareciera una cuenta caliente real. Mi escenario de contención máxima muestra el techo: unas 148 transferencias por segundo sobre una sola fila.
5. **Separar lo que viene después de la transferencia** (notificaciones, riesgo, analítica) a consumidores asíncronos. La transferencia seguiría siendo síncrona y atómica.

Lo que **no** haría es partir el núcleo en microservicios, por lo ya dicho sobre la atomicidad.

### ¿Qué mejorarías para un entorno de producción?

- Alta disponibilidad de la base con réplica y failover probado.
- Revocación de tokens y cookie `httpOnly` en lugar de `sessionStorage`.
- Rate limiting compartido, y probablemente también en un proxy inverso delante.
- Secretos gestionados de verdad, no variables de entorno en un fichero.
- Observabilidad continua: métricas exportadas y trazas, no solo logs correlacionados.
- Reversiones contables como caso de uso de primera clase.
- Y un proceso de despliegue con migraciones compatibles hacia atrás, para poder desplegar sin ventana de parada.

### ¿Qué aporta una arquitectura orientada a eventos?

Desacoplamiento temporal: el productor no espera al consumidor. Es muy buena para lo que ocurre **después** de que el dinero se mueva.

En PayCore encajaría para notificaciones, puntuación de riesgo y analítica. Mi ledger, al ser de solo inserción, ya tiene forma de log de eventos.

Lo que **no** haría es poner la transferencia en sí detrás de un evento. Pasaría de una garantía transaccional a entrega «al menos una vez», con consumidores que tendrían que ser idempotentes y un estado intermedio visible para el usuario. Cambiaría una garantía fuerte por un problema nuevo.

### ¿Cuándo usarías Redis o una cola de mensajes?

**Redis:** cuando el despliegue pase de un proceso y el contador de rate limiting tenga que ser compartido. Ahí sí resuelve un problema real sin romper nada.

**Donde no lo usaría es para la idempotencia**, y esta es la respuesta que más me gusta dar: poner la clave en Redis y el dinero en PostgreSQL deja las dos cosas en sistemas distintos, y reabre exactamente la ventana que el diseño cierra. Si el `COMMIT` tiene éxito y la escritura en Redis falla, el reintento duplica el pago.

**Una cola:** cuando aparezcan consumidores asíncronos reales. Hoy no los hay.

### ¿En qué caso tendría sentido incorporar IA o RAG?

Tengo un límite de diseño escrito y es permanente: **ningún modelo aprueba, rechaza ni modifica una transferencia o un saldo**. Un sistema no determinista no puede estar en la ruta crítica del dinero, porque no es auditable.

Dentro de ese límite, por orden de sensatez:

1. **Reglas deterministas de riesgo** (velocidad de envío, importe atípico frente al propio historial, receptor nuevo) que adjunten una marca de revisión. Baratas, explicables, auditables. Es lo que un sistema real pone primero.
2. **Detección de anomalías no supervisada** como experimento, diciendo con claridad que los datos son sintéticos y que el resultado no generaliza.
3. Un **clasificador supervisado de fraude** necesitaría transacciones reales etiquetadas. No existen y no se pueden fabricar sin falsear el resultado, así que no entra.

**RAG** no tiene sitio aquí: sería infraestructura sin un corpus que consultar.

Sculley et al. (NIPS 2015) documentan que el código de modelo es una fracción pequeña de un sistema de ML y que el resto es deuda de mantenimiento. Incurrir en ella sin datos ni evaluación creíble no aporta nada demostrable.

---

## Parte 3. Preguntas que te pueden incomodar

### «¿Esto no es muy simple? Son dos tablas y un UPDATE.»

El modelo de datos es simple a propósito. Lo que no es simple es lo que lo rodea: que la operación sea atómica bajo fallo, correcta bajo cien peticiones simultáneas sobre la misma fila, y no duplicable cuando el cliente reintenta.

La prueba de que no es trivial es que **tuve un lost update real** con el bloqueo puesto correctamente, y las 76 pruebas que tenía en ese momento pasaban todas.

### «¿Por qué `BIGINT` en céntimos y no `NUMERIC`?»

Las dos son correctas y `NUMERIC` es perfectamente defendible. Elegí enteros porque hacen que la invariante «la suma de los asientos es exactamente cero» sea cierta por construcción en aritmética entera, sin pensar en escalas.

El coste está declarado: no admite fracciones de céntimo. Si hicieran falta intereses o comisiones prorrateadas, la vía sería `NUMERIC` con una política de redondeo explícita, nunca punto flotante.

### «Las dos estrategias dan el mismo resultado correcto. ¿No sobra una?»

Para producción, sí: me quedo con la pesimista. La segunda existe para poder responder con datos a la pregunta «¿por qué pesimista?», en vez de con una preferencia.

Y la medición me dio algo que no esperaba: bajo contención máxima la diferencia en peticiones por segundo parecía de un 57 %, pero contando transferencias realmente confirmadas era del 93 %. Esa brecha es el hallazgo metodológico del proyecto.

### «¿Cuánto de esto funciona de verdad?»

Todo lo que el README dice que funciona. Puedes levantarlo con un comando, cargar datos de prueba y hacer una transferencia. Las 96 pruebas corren en CI contra un PostgreSQL real, y los CSV de las mediciones están versionados para que cualquiera los revise.

Y lo que no está hecho, lo digo: no hay reversiones contables, ni notificaciones, ni recuperación de contraseña, ni verificación de identidad. No están a medias, no existen.

---

## Parte 4. Dos líneas para el CV

Solo con logros comprobables. Las cifras salen de pruebas y CSV versionados.

> **PayCore — Motor transaccional para billetera digital simulada** (Python, FastAPI, PostgreSQL, React)
>
> - Diseñé e implementé un motor de transferencias con libro mayor de doble entrada y control de concurrencia a nivel de base de datos, verificado con 96 pruebas automatizadas contra PostgreSQL real que incluyen 100 peticiones simultáneas sobre una misma cuenta, inyección de fallos antes y después del `COMMIT`, y terminación forzada del proceso de base de datos a mitad de transacción.
> - Detecté y corregí dos defectos de concurrencia mediante pruebas de carga con Locust: una actualización perdida invisible para las pruebas de un solo hilo, y un agotamiento del pool de conexiones cuya corrección multiplicó por 7,4 el rendimiento de lectura y redujo el percentil 99 de 31 000 ms a 840 ms.

**Si necesitas una sola línea:**

> Motor transaccional de billetera simulada (FastAPI, PostgreSQL) con ledger de doble entrada e idempotencia confirmada en la misma transacción; 96 pruebas automatizadas y mediciones de carga que detectaron y corrigieron dos defectos de concurrencia reales.

---

## Parte 5. Repaso de cinco minutos antes de entrar

Cinco cifras que conviene tener en la cabeza:

| Dato | Valor |
|---|---|
| Pruebas automatizadas | 96 |
| Prueba D, aprobadas de 100 | exactamente 3 |
| Transferencias confirmadas/s, pesimista frente a serializable | 148,3 contra 10,4 |
| Mejora al corregir el pool | 7,4 veces, y p99 de 31 000 ms a 840 ms |
| Lost update antes de corregirlo | 88 aprobadas de 100 |

Cinco frases que resumen el proyecto:

1. El dinero se mueve en una sola transacción, y la clave de idempotencia se confirma con él.
2. Nueve de las diez invariantes viven en PostgreSQL, no en Python.
3. Las aserciones sobre dinero consultan la base de datos, no las respuestas HTTP.
4. Medir lo que responde la API no es verificar que el dinero se registró.
5. Cada tecnología que no está tiene escrita la condición bajo la que entraría.
