# Evidencia de ejecución: hitos H1 y H2

Ejecutado el 18 de octubre de 2026 en la máquina de desarrollo.

| Dato | Valor |
|---|---|
| Sistema | Linux 7.0.0-34-generic |
| Python | 3.12.3 |
| PostgreSQL | 16.10-alpine (contenedor) |
| Docker | 29.4.0, Compose v5.1.2 |

## H1. La aplicación arranca con un comando

```
$ docker compose up -d
 Container paycore-db Started
 Container paycore-db Healthy
 Container paycore-api Started
```

Registro de la API al arrancar, con la migración aplicándose sola:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_esquema_inicial, Esquema inicial de PayCore
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Sonda de salud:

```
$ curl -s -i http://localhost:8000/health
HTTP/1.1 200 OK
x-request-id: b4e38047d72b468ca4e79b36e8e35099
content-type: application/json

{"status":"ok","environment":"development","database":"ok","concurrency_strategy":"pessimistic"}
```

Log estructurado en JSON, con identificador de correlación:

```json
{"timestamp": "2026-10-19T00:37:18+0000", "level": "INFO", "logger": "app.api.middleware",
 "message": "peticion", "request_id": "c3264b244dbe475085c3a564fb176d03",
 "method": "GET", "path": "/health", "status": 200, "duracion_ms": 3.54}
```

## H2. Invariantes aplicadas por el motor

Las pruebas de `tests/test_invariantes_esquema.py` no pasan por la aplicación:
atacan PostgreSQL directamente con SQL. Si una restricción solo existiera en el
código Python, fallarían.

Salida completa de `pytest -v`:

```
tests/test_invariantes_esquema.py::test_i1_saldo_de_usuario_no_puede_ser_negativo PASSED [  4%]
tests/test_invariantes_esquema.py::test_i1_la_cuenta_de_sistema_si_puede_quedar_negativa PASSED [  8%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[0] PASSED [ 12%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[-1] PASSED [ 16%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[-5000] PASSED [ 20%]
tests/test_invariantes_esquema.py::test_i3_origen_y_destino_no_pueden_coincidir PASSED [ 25%]
tests/test_invariantes_esquema.py::test_i4_un_solo_asiento_hace_fallar_el_commit PASSED [ 29%]
tests/test_invariantes_esquema.py::test_i4_dos_asientos_que_no_suman_cero_hacen_fallar_el_commit PASSED [ 33%]
tests/test_invariantes_esquema.py::test_i4_el_par_correcto_si_se_confirma PASSED [ 37%]
tests/test_invariantes_esquema.py::test_i4_una_transferencia_no_puede_tocar_dos_veces_la_misma_cuenta PASSED [ 41%]
tests/test_invariantes_esquema.py::test_i10_no_se_puede_actualizar_un_asiento PASSED [ 45%]
tests/test_invariantes_esquema.py::test_i10_no_se_puede_borrar_un_asiento PASSED [ 50%]
tests/test_invariantes_esquema.py::test_una_transferencia_rechazada_debe_llevar_motivo PASSED [ 54%]
tests/test_invariantes_esquema.py::test_una_cuenta_de_usuario_no_puede_quedar_sin_dueno PASSED [ 58%]
tests/test_invariantes_esquema.py::test_un_usuario_solo_puede_tener_una_cuenta_en_el_mvp PASSED [ 62%]
tests/test_invariantes_esquema.py::test_el_correo_es_unico_sin_distinguir_mayusculas PASSED [ 66%]
tests/test_invariantes_esquema.py::test_solo_se_admite_la_moneda_pen_simulada PASSED [ 70%]
tests/test_migraciones.py::test_el_esquema_migrado_coincide_con_los_modelos PASSED [ 75%]
tests/test_migraciones.py::test_la_migracion_es_reversible PASSED        [ 79%]
tests/test_salud_api.py::test_health_responde_ok PASSED                  [ 83%]
tests/test_salud_api.py::test_toda_respuesta_lleva_identificador_de_correlacion PASSED [ 87%]
tests/test_salud_api.py::test_se_respeta_el_identificador_de_correlacion_del_cliente PASSED [ 91%]
tests/test_salud_api.py::test_la_especificacion_openapi_se_genera PASSED [ 95%]
tests/test_salud_api.py::test_una_ruta_inexistente_devuelve_el_formato_de_error_uniforme PASSED [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/manyory/Documentos/PayCore/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 24 passed, 1 warning in 6.19s =========================
```
