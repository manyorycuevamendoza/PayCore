# Comprobación de PayCore — 21 de octubre de 2026

Se comprobó el árbol local, incluidas las modificaciones de interfaz aún sin
commit. Esta revisión no cambió el código de la aplicación. Las pruebas de
backend recrearon exclusivamente `paycore_test` según `tests/conftest.py`.

## Comprobaciones aprobadas

| Comprobación | Resultado |
|---|---|
| `./.venv/bin/python -m pytest -v --junitxml=/tmp/paycore-audit-pytest.xml` | 96 aprobadas; 16,52 s; una advertencia de deprecación de Starlette/TestClient con httpx |
| `docker compose exec -T web npm test` | 4 aprobadas |
| `docker compose exec -T web npm run typecheck` | Sin errores |
| `docker compose exec -T web npm run build` | Compilación correcta |
| Comparar `create_app().openapi()` con `docs/openapi.json` | Coinciden |
| `python -m pip check` desde `.venv` | Sin dependencias incompatibles detectadas |
| Sintaxis de scripts de arranque, parada, seed, reset y exportación OpenAPI | Correcta |
| `node --check scripts/capturas.mjs` | Sintaxis correcta; esto no comprueba sus selectores |
| `git diff --check` | Sin errores de espacios |
| Estado Compose | API y PostgreSQL healthy; frontend activo |
| HTTP interfaz, salud y documentación | 200 |
| Salud de la API | `status=ok`, `database=ok`, estrategia `pessimistic` |
| Consulta de cuenta sin token | 401, con request_id y CORS |

Último CI remoto de main consultado: `success`, commit
`087721028de348d4379509dc4db82a09b4005ccf`.
[Ejecución](https://github.com/manyorycuevamendoza/PayCore/actions/runs/39622429286).
No incluye los cambios locales de Norman.

## Problemas encontrados

### 1. El límite de tamaño puede eludirse al no enviar Content-Length

Prioridad alta. `backend/app/api/middleware.py:57` solo comprueba el tamaño
declarado, pese a que su documentación también promete limitar durante la lectura.

Reproducción aislada con la aplicación real creada por `create_app()` y una ruta
exclusiva de diagnóstico que lee el cuerpo; no se añadieron rutas al servidor en
funcionamiento. Se enviaron 16 385 bytes para un límite de 16 384:

- Con `Content-Length`: respuesta 413, correcta.
- Sin `Content-Length`, con `Transfer-Encoding: chunked`: respuesta 200 y lectura
  del cuerpo completo. Se esperaba 413.

El problema permite que una petición grande llegue al procesamiento y consuma
memoria. La suite existente no detectó esta diferencia.

### 2. Los errores inesperados 500 pierden correlación y CORS

Prioridad alta para diagnóstico y recuperación del cliente.
`backend/app/api/middleware.py:25` restaura el contexto antes de que el manejador
externo de errores inesperados genere la respuesta. El manejador está en
`backend/app/api/errors.py:90`; CORS se registra dentro de esa capa en
`backend/app/main.py:76`.

Reproducción aislada: una ruta exclusiva de diagnóstico lanza `RuntimeError`;
`TestClient(..., raise_server_exceptions=False)` hace GET con
`X-Request-ID: auditoria-error-500` y `Origin: http://localhost:5173`.

Resultado observado:

```json
{"status": 500, "header_request_id": null, "body_request_id": "-", "cors": null}
```

El log `error_no_controlado` conserva el stack trace, pero también tiene
`request_id: "-"`. Falta la cabecera `Access-Control-Allow-Origin` incluso para
el origen permitido; esto impide al frontend de otro puerto leer esa respuesta.
Los errores controlados y las respuestas normales sí pasaron las comprobaciones.

### 3. El script de capturas quedó desactualizado con el rediseño

Prioridad media. Inspección estática, sin ejecutar navegador.
`scripts/capturas.mjs:26` busca el botón «Entrar», ahora «Iniciar sesión».
Las líneas 73–85 buscan «Alias de destino», «Importe en soles simulados» y un
solo botón «Enviar»; la interfaz ahora usa otras etiquetas y revisión previa.
El caso de saldo insuficiente espera una respuesta del servidor, pero la interfaz
ahora bloquea antes de enviar. Estos selectores y el recorrido ya no coinciden.

Es una regresión introducida por el cambio de interfaz de esta sesión.
La sintaxis válida del script no garantiza que ese recorrido funcione.

### 4. El CI no ejecuta las nuevas pruebas de frontend

Prioridad media; hueco de cobertura, no ejecución fallida.
`.github/workflows/ci.yml:83` instala dependencias, comprueba tipos y compila,
pero no incluye `npm test`. Las cuatro pruebas nuevas solo se han ejecutado
localmente en el contenedor.

## Límites de esta comprobación

No hay navegadores disponibles en la herramienta de interfaz. No se pudieron
comprobar visualmente los temas, el diseño móvil ni los recorridos de teclado,
lector de pantalla y pérdida de conexión del frontend. Tampoco se repitieron
las mediciones de carga de 60 segundos; sí las pruebas automatizadas de concurrencia.

La operación incierta del frontend sigue guardándose en memoria del componente
(`frontend/src/components/Transferir.tsx:30`): recargar o cerrar sesión pierde
el contexto de reintento. Es una limitación conocida y requiere recuperación
persistente si se quiere cubrir ese escenario.

La revisión y las pruebas aprobadas no equivalen a una garantía de ausencia de
errores ni a una auditoría exhaustiva de seguridad.
