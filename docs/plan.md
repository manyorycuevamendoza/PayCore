# PayCore. Plan de construcción

Estado al 18 de octubre de 2026.

## Estado por fase

| Fase | Entregable | Estado |
|---|---|---|
| 1. Investigación | [docs/research.md](research.md) | **Completada** |
| 2. Justificación del stack | [docs/stack.md](stack.md), 8 ADRs en [docs/decisions/](decisions/) | **Completada** |
| 3. Diseño funcional | [docs/architecture.md](architecture.md) | **Completada** (diseño propuesto, sin código) |
| 4. Backend | API FastAPI, migraciones, invariantes | **En curso** (H1 a H6 hechos; faltan H7 concurrencia, H8 fallos y H9 rate limiting) |
| 5. Interfaz web | React + Vite | Pendiente |
| 6. Pruebas A-F | Suite pytest | **En curso**: A, B, C y F hechas y verificadas. Faltan D (concurrencia) y E (fallos) |
| 7. Rendimiento | Locust, CSV y gráficos reales | Pendiente |
| 8. Informe LaTeX | `docs/latex/main.tex` + PDF | Pendiente |
| 9. README | `README.md` con capturas reales | Pendiente |
| 10. Preparación de entrevista | `docs/interview-preparation.md` | Pendiente |
| 11. Organización y entrega | CI, `.env.example`, scripts, evidencia | Pendiente |

## Hitos de implementación

### H1. Esqueleto ejecutable — **completado**
`docker compose up` levanta PostgreSQL y el backend. `GET /health` responde 200. Alembic con la migración inicial aplicada.
**Criterio de aceptación:** un clon limpio del repositorio llega a `/health` 200 con un solo comando.
**Verificado:** sí. Ver [docs/evidence/h1-h2-pruebas.md](evidence/h1-h2-pruebas.md). Añadidos además logging JSON con `X-Request-ID`, manejo centralizado de errores con formato uniforme y OpenAPI versionada en `docs/openapi.json` con comprobación de desincronización en CI.

### H2. Esquema y invariantes en el motor — **completado**
Tablas `users`, `accounts`, `transfers`, `ledger_entries`, `idempotency_keys` con todas las restricciones `CHECK` de la sección 3.1 de architecture.md, y el trigger que impide `UPDATE`/`DELETE` sobre el ledger.
**Criterio:** pruebas que intentan violar cada invariante directamente por SQL y reciben error del motor, sin pasar por la aplicación.
**Verificado:** 24 pruebas en verde. Además del trigger de solo inserción se añadió `trg_ledger_balanced`, un trigger de restricción `DEFERRABLE INITIALLY DEFERRED` que al `COMMIT` rechaza cualquier transferencia cuyos asientos no sean exactamente dos y no sumen cero (invariante I4 aplicada por el motor, no por Python). También hay prueba de que el esquema migrado no diverge de los modelos y de que la migración es reversible.

### H3. Identidad — **completado**
Registro, login, Argon2id con los parámetros de OWASP, emisión y verificación de JWT, dependencia de autenticación a nivel de router.
**Criterio:** pruebas de token ausente, expirado y con firma inválida.
**Verificado:** 13 pruebas. Una de ellas lee el hash directamente de la base y comprueba que empieza por `$argon2id$` y lleva `m=19456,t=2,p=1`, los parámetros citados de OWASP. Correo y contraseña incorrectos devuelven el mismo error para no permitir enumerar cuentas. Se añadió validación de longitud mínima del secreto JWT (32 bytes, RFC 7518 §3.2), que saltó porque PyJWT avisaba de una clave corta en las pruebas.

### H4. Transferencia, camino feliz — **completado**
Caso de uso completo con estrategia pesimista, asientos de doble entrada, saldo materializado, todo en una transacción.
**Criterio:** Prueba A verificada **en la base de datos**: Ana 7000 ctms, Luis 5000 ctms, dos asientos con `transfer_id` común que suman cero.
**Verificado:** sí, y además con `curl` contra el stack real levantado en Docker. Ver [docs/evidence/h3-h6-pruebas.md](evidence/h3-h6-pruebas.md). El bloqueo se adquiere con dos sentencias `SELECT ... FOR UPDATE` separadas en orden ascendente de identificador, y no con un único `WHERE id IN (...) ORDER BY id FOR UPDATE`, porque el orden en que PostgreSQL bloquea un conjunto depende del plan y no está garantizado.

### H5. Rechazos y autorización — **completado**
Fondos insuficientes, origen igual a destino, importes inválidos, cuenta ajena.
**Criterio:** Pruebas B y F. En B los saldos deben quedar **idénticos** a los previos, verificado por consulta directa.
**Verificado:** 19 pruebas de seguridad organizadas por riesgo del OWASP API Top 10 2023. La transferencia rechazada se persiste con `status='rejected'` y cero asientos, de modo que queda en el historial sin tocar el saldo. Los importes inválidos (cero, negativos, decimales, fuera de rango, texto) se rechazan con 422 sin redondear nada en el servidor.

### H6. Idempotencia — **completado**
Tabla, reclamación con `ON CONFLICT DO NOTHING`, reproducción de respuesta, 409 para `in_progress`, 422 para huella distinta.
**Criterio:** Prueba C (reintento secuencial, un solo asiento par) y prueba de dos peticiones **simultáneas** con la misma clave.
**Verificado:** 10 pruebas, incluida la concurrente con dos hilos y dos conexiones reales, en la que exactamente una reclama la clave. También se cubre que el rechazo 422 por fondos es idempotente, que el orden de los campos del JSON no cambia la huella, y que la clave de un usuario no sirve a otro. Caso que apareció al implementar y que el diseño no había previsto: si el `INSERT` choca con una fila que otra transacción aún no ha confirmado, en READ COMMITTED el `SELECT` posterior no la ve; se trata como petición en curso (409), que es la semántica correcta.

### H7. Concurrencia
Orden determinista de bloqueo. Estrategia `serializable` con reintento ante 40001.
**Criterio:** Prueba D con 100 peticiones concurrentes de 3000 ctms contra una cuenta de 10000 ctms: como máximo 3 confirmadas, saldo final 1000 ctms, reconciliación cuadrada. Prueba de transferencias cruzadas sin deadlock.

### H8. Pruebas de fallo
Inyección de fallo antes del `COMMIT`, después del `COMMIT` y antes de entregar la respuesta.
**Criterio:** Prueba E. Tras el fallo previo al commit, cero asientos. Tras el fallo posterior al commit, el reintento con la misma clave devuelve la respuesta original y **no** crea asientos nuevos.

### H9. Rate limiting y manejo de errores
Límite por usuario e IP en login y transferencias, formato uniforme de error, `request_id` correlacionado en logs JSON.
**Criterio:** prueba que satura el límite y espera 429. Prueba que afirma que ninguna respuesta de error contiene traza.

### H10. Frontend
Login, panel, saldo, formulario de transferencia, confirmación, historial, estados de error y de carga, aviso de prototipo educativo con fondos simulados.
**Criterio:** recorrido manual completo con capturas reales que se usarán en el README y en el informe.

### H11. Rendimiento
Escenarios Locust, ejecución de las dos estrategias de concurrencia bajo carga equivalente, CSV crudos versionados, gráficos generados por script a partir de esos CSV, y reconciliación en base de datos después de cada ejecución.
**Criterio:** tabla con RPS, transferencias confirmadas por segundo, p50, p95, p99, errores por segundo y tasa de fallo, con la máquina y las versiones documentadas. Ningún número que no provenga de un CSV del repositorio.

### H12. Documentación e informe
Informe LaTeX compilable, README, preparación de entrevista, workflow de CI con PostgreSQL como servicio, `.env.example`, script de inicialización, datos ficticios e instrucciones de limpieza.
**Criterio:** `latexmk -pdf` produce el PDF sin errores y el CI está en verde.

## Riesgos abiertos y decisiones pendientes

| Riesgo | Plan |
|---|---|
| `biber` no instalado | BibLaTeX con `backend=bibtex`. Se intentará primero `apt install biber`; si no es posible, se documenta la configuración alternativa |
| Inestabilidad de las pruebas de concurrencia en CI | Aserciones sobre estado final determinista, nunca sobre entrelazado |
| Medir rendimiento en runners compartidos | Las cifras se toman en hardware local documentado; en CI solo una prueba de humo |
| Alcance total frente a tiempo | El orden H1-H9 produce un MVP defendible aunque H10-H12 se recorten. No se recortará ninguna de las pruebas A-F |
