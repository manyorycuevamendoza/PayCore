# PayCore. Justificación del stack tecnológico y matriz de decisiones (Fase 2)

Este documento responde, para cada tecnología, las ocho preguntas obligatorias. Las fuentes se identifican con los mismos códigos que [docs/research.md](research.md).

Regla de admisión aplicada: **una tecnología entra solo si hay un requisito del enunciado o un experimento planificado que la necesite.** Al final del documento se listan explícitamente las tecnologías descartadas y bajo qué condición volverían a considerarse.

---

## 1. Matriz de decisiones tecnológicas

Puntuación de 1 a 5 donde 5 es mejor. "Ajuste" mide cuánto resuelve el problema concreto de PayCore; "Coste" mide coste operativo y de complejidad invertido (5 = coste muy bajo).

| Componente | Elegida | Ajuste | Madurez | Coste | Evidencia | Alternativa principal descartada | Motivo del descarte |
|---|---|---|---|---|---|---|---|
| Lenguaje | Python 3.12 | 4 | 5 | 5 | Ecosistema de pruebas y de carga en el mismo lenguaje | Go, Java/Spring | Go: menos ergonómico para Alembic/Locust. Java: más ceremonia para el alcance |
| Framework HTTP | FastAPI | 5 | 4 | 5 | OpenAPI automática, validación en el borde [FASTAPI] | Django REST, Flask | Django: ORM y admin que no usaríamos. Flask: validación y OpenAPI manuales |
| Base de datos | PostgreSQL 16 | 5 | 5 | 4 | `SERIALIZABLE` real vía SSI [PG-SSI], `FOR UPDATE` [PG-LOCK], WAL [PG-WAL] | MySQL/InnoDB, SQLite, MongoDB | MySQL: sin SSI. SQLite: concurrencia de escritura por fichero, invalida la Prueba D. MongoDB: transacciones multidocumento con más caveats y sin `CHECK` |
| Acceso a datos | SQLAlchemy 2.x | 5 | 5 | 4 | `with_for_update()` verificado, aislamiento por transacción [SA-TX] | SQL crudo con psycopg, Tortoise, SQLModel | SQL crudo: más riesgo de concatenación. Tortoise: menor control de bloqueos. SQLModel: capa extra sobre lo mismo |
| Migraciones | Alembic | 5 | 5 | 5 | Migraciones versionadas y reversibles [ALEMBIC] | SQL manual numerado | Pierde la generación asistida y la reversión |
| Hash de contraseñas | Argon2id (`argon2-cffi`) | 5 | 5 | 5 | Primera recomendación de OWASP con parámetros citados [OWASP-PWD] | bcrypt | Recomendado por OWASP solo para sistemas heredados, y con el límite de 72 bytes |
| Sesión | JWT HS256 de vida corta | 4 | 5 | 5 | Sin estado de servidor, suficiente para un solo servicio | Cookie de sesión en BD | Añade una lectura por petición; se documenta como la opción correcta si hiciera falta revocación inmediata |
| Frontend | React 18 + Vite + TypeScript | 4 | 5 | 4 | Exigido por el enunciado | Plantillas Jinja en el backend | Menos demostrable como competencia, y el enunciado pide React |
| Contenedores | Docker Compose | 5 | 5 | 4 | Un comando reproduce el entorno completo | Instalación local de PostgreSQL | No reproducible para un tercero que clone el repositorio |
| Pruebas | Pytest | 5 | 5 | 5 | Fixtures, parametrización, marcadores para separar niveles | unittest | Más verboso, peores fixtures |
| Carga | Locust | 5 | 4 | 4 | Escenarios en Python, modelo gevent, exportación de resultados [LOCUST] | k6, JMeter | k6: escenarios en JS, otro lenguaje más. JMeter: XML y mayor peso |
| Documentación API | OpenAPI 3.1 | 5 | 5 | 5 | Generada por FastAPI y versionada en el repositorio | Markdown a mano | Se desincroniza del código |
| Observabilidad | Logs JSON + `/metrics` en texto plano | 4 | 4 | 5 | Suficiente para correlacionar y para la Fase 7 | Prometheus + Grafana | Dos servicios más para un prototipo de una persona. Se documenta como siguiente paso |
| CI | GitHub Actions | 5 | 5 | 5 | PostgreSQL como servicio en el runner, gratuito en repositorio público | CI local | Sin evidencia pública de que las pruebas pasan |

---

## 2. Ficha por tecnología

### 2.1 PostgreSQL 16

1. **Problema que resuelve.** Persistir el dinero simulado con garantías ACID y aislamiento configurable, y permitir que las invariantes vivan en el motor y no solo en Python.
2. **Por qué la elegimos.** Es el único candidato del conjunto evaluado que ofrece a la vez: `SELECT FOR UPDATE` con semántica documentada [PG-LOCK], un `SERIALIZABLE` genuino implementado mediante Serializable Snapshot Isolation [PG-SSI], restricciones `CHECK`, tipos exactos para dinero [PG-MONEY] y durabilidad por WAL [PG-WAL]. El proyecto necesita las dos estrategias de concurrencia para poder compararlas.
3. **Alternativas consideradas.** MySQL/InnoDB, SQLite, MongoDB, CockroachDB.
4. **Ventajas.** Las dos estrategias de concurrencia medibles en el mismo motor. `CHECK` como última línea de defensa. `EXPLAIN ANALYZE` para la Fase 7.
5. **Limitaciones.** Una sola instancia es un punto único de fallo y el techo de escritura es el de un nodo. Operar PostgreSQL en producción (vacuum, réplicas, failover) tiene coste real que este prototipo no asume.
6. **Coste.** Un contenedor en Compose. Sin coste de licencia.
7. **Fundamento.** [PG-SSI] documenta la implementación de SSI y reporta un coste de menos del 7% frente a snapshot isolation. [BER95] fundamenta por qué esa distinción importa.
8. **Cómo comprobamos que cumple.** Prueba D sobre la base de datos: 100 peticiones concurrentes de S/30 contra una cuenta con S/100 deben dejar como máximo 3 transferencias confirmadas y saldo S/10. Prueba de reconciliación: `SUM(ledger_entries) = 0`.

### 2.2 FastAPI

1. **Problema.** Exponer la API REST con validación en el borde y documentación que no se desincronice.
2. **Por qué.** Genera OpenAPI 3.1 desde los propios tipos, valida con Pydantic antes de que la petición llegue al dominio, y su sistema de dependencias permite aplicar autenticación a nivel de router (mitigación directa de API5:2023 [OWASP-API]).
3. **Alternativas.** Django REST Framework, Flask + marshmallow, Litestar.
4. **Ventajas.** Menos código de validación escrito a mano. La especificación OpenAPI es un artefacto versionable y diffeable en CI.
5. **Limitaciones.** El soporte asíncrono invita a mezclar código bloqueante y no bloqueante. Decisión tomada: **endpoints síncronos** con SQLAlchemy síncrono, ejecutados en el threadpool de Starlette, para evitar el riesgo de bloquear el bucle de eventos con el driver de base de datos. Se documenta como trade-off deliberado.
6. **Coste.** Bajo. Una dependencia y un servidor ASGI.
7. **Fundamento.** [FASTAPI].
8. **Comprobación.** La especificación OpenAPI se genera en CI y se compara con la versionada; las pruebas de contrato validan los códigos de respuesta documentados.

### 2.3 SQLAlchemy 2.x y Alembic

1. **Problema.** Mapear el dominio a tablas sin construir SQL por concatenación, controlar explícitamente la transacción y el bloqueo, y versionar el esquema.
2. **Por qué.** Control fino del límite transaccional (`Session.begin()`, `begin_nested()`), aislamiento configurable por transacción con `session.connection(execution_options={"isolation_level": ...})` [SA-TX], y `with_for_update()` verificado en este entorno (SQLAlchemy 2.1.5) como generador de `FOR UPDATE` en PostgreSQL. Alembic da migraciones reversibles y revisables.
3. **Alternativas.** psycopg con SQL crudo, Tortoise ORM, SQLModel.
4. **Ventajas.** Parámetros vinculados por defecto, lo que elimina la inyección SQL por construcción. La unidad de trabajo encaja con "una transferencia = una transacción".
5. **Limitaciones.** Un ORM puede ocultar cuántas consultas se emiten. Mitigación: el caso de uso de transferencia se escribe con sentencias explícitas y se revisa su SQL generado.
6. **Coste.** Curva de aprendizaje de la API 2.x.
7. **Fundamento.** [SA-TX] y verificación empírica registrada en research.md.
8. **Comprobación.** Prueba que ejecuta `alembic upgrade head` sobre una base vacía y después `alembic downgrade base`, y prueba que afirma que el esquema generado por los modelos no tiene diferencias contra el esquema migrado.

### 2.4 Pytest

1. **Problema.** Automatizar las pruebas A a F y separarlas por nivel.
2. **Por qué.** Fixtures componibles para base de datos por prueba, y marcadores (`unit`, `integration`, `concurrency`, `security`) para ejecutar subconjuntos.
3. **Alternativas.** unittest.
4. **Ventajas.** Las pruebas de concurrencia necesitan varias conexiones reales en paralelo, y las fixtures permiten montarlo sin duplicar código.
5. **Limitaciones.** Las pruebas de concurrencia son por naturaleza sensibles al entorno; se diseñan para ser deterministas en su aserción final (saldo exacto) aunque el entrelazado varíe.
6. **Coste.** Bajo.
7. **Fundamento.** Documentación oficial de pytest.
8. **Comprobación.** El propio CI. La evidencia de ejecución se archiva en `docs/evidence/`.

### 2.5 Locust

1. **Problema.** Medir rendimiento bajo carga sostenida y comparar la estrategia pesimista contra la optimista con datos propios.
2. **Por qué.** Escenarios escritos en Python, el mismo lenguaje del backend y de las pruebas; modelo basado en gevent que permite muchos usuarios simulados por proceso; exportación de resultados para generar tablas y gráficos [LOCUST].
3. **Alternativas.** k6, JMeter, wrk.
4. **Ventajas.** El mismo escenario puede reutilizar la lógica de generación de claves de idempotencia del cliente.
5. **Limitaciones importantes y declaradas.** (a) Locust mide la respuesta de la API, no si el dinero quedó correctamente registrado; por eso cada ejecución de carga irá seguida de una **verificación de reconciliación en la base de datos**. (b) Las herramientas de carga de bucle cerrado están sujetas a omisión coordinada: si el servidor se ralentiza, el generador deja de emitir y las latencias altas quedan subrepresentadas. Se documenta y se reportan percentiles p50, p95 y p99 junto con el throughput, nunca la media sola. La relevancia de las colas altas está argumentada en [DEAN13].
6. **Coste.** Una dependencia de desarrollo.
7. **Fundamento.** [LOCUST], [DEAN13].
8. **Comprobación.** Las ejecuciones producen CSV reales en `performance/results/`. *Pendiente de medición, Fase 7.*

### 2.6 React 18 + Vite + TypeScript

1. **Problema.** Interfaz de uso para login, saldo, transferencia e historial.
2. **Por qué.** Exigido por el enunciado. TypeScript permite derivar los tipos del cliente desde la especificación OpenAPI, de modo que un cambio de contrato rompa la compilación en lugar de romper en ejecución.
3. **Alternativas.** Plantillas Jinja servidas por FastAPI, Vue, Svelte.
4. **Ventajas.** Separación clara entre API y cliente, que es también lo que fuerza a no poner lógica de negocio en el frontend.
5. **Limitaciones.** Un segundo ecosistema de dependencias que mantener y auditar.
6. **Coste.** Un contenedor más en Compose para desarrollo.
7. **Fundamento.** Requisito del enunciado (Fase 5).
8. **Comprobación.** La interfaz debe mostrar correctamente los cuatro estados de una transferencia (cargando, éxito, fondos insuficientes, error de red) y el aviso de prototipo educativo.

### 2.7 Docker Compose

1. **Problema.** Que cualquiera pueda levantar PayCore con un comando y obtener el mismo entorno.
2. **Por qué.** Define PostgreSQL, backend y frontend con versiones fijadas. Es también lo que hace reproducibles las pruebas de carga.
3. **Alternativas.** Instalación manual, Kubernetes, devcontainers.
4. **Ventajas.** Reproducibilidad y aislamiento del PostgreSQL del sistema.
5. **Limitaciones.** No representa un despliegue de producción. Se declara explícitamente en el README.
6. **Coste.** Bajo.
7. **Fundamento.** Documentación de Docker Compose.
8. **Comprobación.** Un script de arranque limpio desde cero que termina con la aplicación respondiendo y los datos de prueba cargados.

### 2.8 GitHub Actions

1. **Problema.** Evidencia pública y automática de que el proyecto compila y las pruebas pasan.
2. **Por qué.** Permite levantar PostgreSQL como servicio del runner, por lo que las pruebas de integración y concurrencia se ejecutan de verdad en CI, no solo las unitarias.
3. **Alternativas.** GitLab CI, ejecución local.
4. **Ventajas.** Un reclutador ve el estado del pipeline sin ejecutar nada.
5. **Limitaciones.** Los runners compartidos no son un entorno fiable para **medir rendimiento**. Las cifras de la Fase 7 se tomarán en hardware local documentado, y el CI solo ejecutará una prueba de humo de carga.
6. **Coste.** Gratuito en repositorio público.
7. **Fundamento.** Documentación de GitHub Actions.
8. **Comprobación.** Insignia de estado en el README enlazada al workflow real.

---

## 3. Tecnologías descartadas y condición de reingreso

| Tecnología | Por qué no entra ahora | Qué tendría que pasar para incorporarla |
|---|---|---|
| **Redis** | Como caché, no hay problema de lectura que resolver. Como almacén de idempotencia, **rompería la atomicidad**, porque la clave y el movimiento de dinero quedarían en sistemas distintos y reaparecería la ventana de fallo que el diseño cierra. Como rate limiter distribuido sí resolvería algo real, pero solo cuando haya más de un proceso de API | Que la medición de la Fase 7 demuestre contención en lecturas, o que el despliegue pase a varias réplicas y el rate limiting deba ser compartido |
| **Kafka / RabbitMQ** | No hay consumidores asíncronos en el MVP. La transferencia debe ser síncrona y atómica | Que se añadan notificaciones, antifraude asíncrono o un servicio de analítica |
| **Kubernetes** | Un despliegue, una base de datos. Compose cubre el caso | Despliegue real multirréplica con necesidad de autoescalado |
| **Microservicios** | Rompe la atomicidad de la transferencia y obliga a Saga o 2PC [FOW15] | Equipos independientes y fronteras de dominio validadas por uso real |
| **Servicios cloud de pago** | Coste y ninguna capacidad necesaria que no esté cubierta localmente | Necesidad de demostrar un despliegue público |
| **Prometheus + Grafana** | Dos servicios más por métricas que en esta escala se cubren con logs estructurados y los CSV de Locust | Operación continua del sistema, no solo experimentos puntuales |
| **Cualquier modelo de IA en la ruta del dinero** | Límite de diseño duro, ver research.md sección 6 | No aplica. La restricción es permanente |

---

## 4. Riesgos del stack y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| `biber` no está instalado en el entorno de trabajo | La Fase 8 podría no compilar con BibLaTeX en su configuración habitual | Configurar BibLaTeX con `backend=bibtex`, que sí está disponible, y documentar el comando de instalación de `biber` como alternativa preferida |
| Las pruebas de concurrencia pueden ser inestables en CI | Falsos rojos | Aserciones sobre el estado final de la base de datos (determinista) y no sobre el entrelazado; tiempos de espera generosos; reintento del job marcado como tal si ocurre |
| Mezcla de código asíncrono y bloqueante en FastAPI | Degradación de latencia difícil de diagnosticar | Decisión explícita de endpoints síncronos con SQLAlchemy síncrono |
| Medición de rendimiento en hardware compartido | Números no comparables | Todas las cifras de la Fase 7 se toman en la misma máquina, documentando CPU, RAM y versiones, y se publican los CSV crudos |
