# Evidencia de ejecución: hitos H3 a H6

Ejecutado el 18 de octubre de 2026. Python 3.12.3, PostgreSQL 16.10-alpine en
contenedor, Docker 29.4.0.

Cubre identidad (H3), transferencia (H4), rechazos y autorización (H5) e
idempotencia (H6). Corresponde a las pruebas A, B, C y F del enunciado.

## Recorrido completo contra el stack real

No es el cliente de pruebas: es `curl` contra la API levantada con
`docker compose`, y las comprobaciones finales son consultas a PostgreSQL.

Datos de partida cargados con `./scripts/seed.sh`: Ana S/100, Luis S/20,
Rosa S/250, todo acreditado desde la cuenta de sistema `SYSTEM_FUNDING`.

### 1. Login

```
$ curl -s -X POST .../auth/login -d '{"email":"ana@ejemplo.pe","password":"PayCoreDemo2026"}'
token de 243 caracteres
```

### 2. Saldo inicial de Ana

```json
{
    "account_id": "d98d124d-3b9d-45ff-9899-66be3e8f3a5f",
    "currency": "PEN",
    "balance_cents": 10000,
    "balance_display": "100.00",
    "as_of": "2026-10-19T00:57:44.933834Z"
}
```

### 3. Prueba A. Transferencia de S/30 a Luis

```json
{
    "id": "05aa9758-81ef-4496-8559-9ed533e24cc9",
    "status": "completed",
    "amount_cents": 3000,
    "amount_display": "30.00",
    "currency": "PEN",
    "source_alias": "ana",
    "destination_alias": "luis",
    "concept": "Almuerzo",
    "created_at": "2026-10-19T00:57:45.035817Z",
    "completed_at": "2026-10-19T00:57:45.051297Z",
    "source_balance_after_cents": 7000,
    "rejection_reason": null
}
```

### 4. Prueba C. La misma clave de idempotencia otra vez

```
HTTP/1.1 201 Created
idempotent-replay: true
```

Mismo cuerpo de respuesta, sin mover el saldo por segunda vez.

### 5. Prueba B. Intento de enviar S/5000 teniendo S/70

```json
{
    "error": {
        "code": "insufficient_funds",
        "message": "El saldo disponible no cubre el importe solicitado.",
        "request_id": "85006c24b5494c3c89ecdc64df8a5cb6",
        "details": {
            "transfer_id": "6afe86ca-879b-40c2-b845-9aa5bc6239be",
            "status": "rejected",
            "rejection_reason": "insufficient_funds",
            "balance_cents": 7000,
            "amount_cents": 500000
        }
    }
}
```

### 6. Estado real en PostgreSQL

Esta es la comprobación que importa. Las respuestas HTTP de arriba no prueban
nada sobre el dinero por sí solas.

```
     alias      |  kind  | balance_cents
----------------+--------+---------------
 SYSTEM_FUNDING | system |        -37000
 ana            | user   |          7000
 luis           | user   |          5000
 rosa           | user   |         25000

 suma_global_ledger
--------------------
                  0

 veces_que_se_movio_el_almuerzo
--------------------------------
                              1
```

Ana S/70 y Luis S/50, que es exactamente el resultado esperado de la Prueba A.
El ledger suma cero: el saldo negativo de `SYSTEM_FUNDING` es, al céntimo, el
total acreditado a las tres personas. Y el almuerzo se movió una sola vez pese
a haberse enviado dos veces.

## Suite completa

```
tests/test_idempotencia.py::test_prueba_c_el_reintento_con_la_misma_clave_no_duplica PASSED [  1%]
tests/test_idempotencia.py::test_el_rechazo_por_fondos_tambien_es_idempotente PASSED [  2%]
tests/test_idempotencia.py::test_misma_clave_con_cuerpo_distinto_devuelve_422 PASSED [  3%]
tests/test_idempotencia.py::test_el_orden_de_los_campos_no_cambia_la_huella PASSED [  5%]
tests/test_idempotencia.py::test_una_peticion_en_curso_con_la_misma_clave_devuelve_409 PASSED [  6%]
tests/test_idempotencia.py::test_la_clave_es_privada_de_cada_usuario PASSED [  7%]
tests/test_idempotencia.py::test_claves_de_longitud_invalida[] PASSED    [  9%]
tests/test_idempotencia.py::test_claves_de_longitud_invalida[corta] PASSED [ 10%]
tests/test_idempotencia.py::test_claves_de_longitud_invalida[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx] PASSED [ 11%]
tests/test_idempotencia.py::test_dos_peticiones_simultaneas_con_la_misma_clave_solo_mueven_dinero_una_vez PASSED [ 13%]
tests/test_identidad.py::test_registro_crea_usuario_y_cuenta_con_saldo_cero PASSED [ 14%]
tests/test_identidad.py::test_la_contrasena_se_guarda_con_argon2id_y_nunca_en_claro PASSED [ 15%]
tests/test_identidad.py::test_no_se_puede_repetir_el_correo PASSED       [ 17%]
tests/test_identidad.py::test_el_correo_no_distingue_mayusculas PASSED   [ 18%]
tests/test_identidad.py::test_no_se_puede_repetir_el_alias PASSED        [ 19%]
tests/test_identidad.py::test_login_con_contrasena_incorrecta PASSED     [ 21%]
tests/test_identidad.py::test_login_con_correo_inexistente_da_el_mismo_error PASSED [ 22%]
tests/test_identidad.py::test_sin_token_no_se_accede[/api/v1/accounts/me] PASSED [ 23%]
tests/test_identidad.py::test_sin_token_no_se_accede[/api/v1/accounts/me/balance] PASSED [ 25%]
tests/test_identidad.py::test_sin_token_no_se_accede[/api/v1/accounts/me/transactions] PASSED [ 26%]
tests/test_identidad.py::test_token_con_firma_invalida PASSED            [ 27%]
tests/test_identidad.py::test_token_caducado PASSED                      [ 28%]
tests/test_identidad.py::test_el_registro_rechaza_contrasenas_cortas PASSED [ 30%]
tests/test_invariantes_esquema.py::test_i1_saldo_de_usuario_no_puede_ser_negativo PASSED [ 31%]
tests/test_invariantes_esquema.py::test_i1_la_cuenta_de_sistema_si_puede_quedar_negativa PASSED [ 32%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[0] PASSED [ 34%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[-1] PASSED [ 35%]
tests/test_invariantes_esquema.py::test_i2_importe_de_transferencia_debe_ser_positivo[-5000] PASSED [ 36%]
tests/test_invariantes_esquema.py::test_i3_origen_y_destino_no_pueden_coincidir PASSED [ 38%]
tests/test_invariantes_esquema.py::test_i4_un_solo_asiento_hace_fallar_el_commit PASSED [ 39%]
tests/test_invariantes_esquema.py::test_i4_dos_asientos_que_no_suman_cero_hacen_fallar_el_commit PASSED [ 40%]
tests/test_invariantes_esquema.py::test_i4_el_par_correcto_si_se_confirma PASSED [ 42%]
tests/test_invariantes_esquema.py::test_i4_una_transferencia_no_puede_tocar_dos_veces_la_misma_cuenta PASSED [ 43%]
tests/test_invariantes_esquema.py::test_i10_no_se_puede_actualizar_un_asiento PASSED [ 44%]
tests/test_invariantes_esquema.py::test_i10_no_se_puede_borrar_un_asiento PASSED [ 46%]
tests/test_invariantes_esquema.py::test_una_transferencia_rechazada_debe_llevar_motivo PASSED [ 47%]
tests/test_invariantes_esquema.py::test_una_cuenta_de_usuario_no_puede_quedar_sin_dueno PASSED [ 48%]
tests/test_invariantes_esquema.py::test_un_usuario_solo_puede_tener_una_cuenta_en_el_mvp PASSED [ 50%]
tests/test_invariantes_esquema.py::test_el_correo_es_unico_sin_distinguir_mayusculas PASSED [ 51%]
tests/test_invariantes_esquema.py::test_solo_se_admite_la_moneda_pen_simulada PASSED [ 52%]
tests/test_migraciones.py::test_el_esquema_migrado_coincide_con_los_modelos PASSED [ 53%]
tests/test_migraciones.py::test_la_migracion_es_reversible PASSED        [ 55%]
tests/test_salud_api.py::test_health_responde_ok PASSED                  [ 56%]
tests/test_salud_api.py::test_toda_respuesta_lleva_identificador_de_correlacion PASSED [ 57%]
tests/test_salud_api.py::test_se_respeta_el_identificador_de_correlacion_del_cliente PASSED [ 59%]
tests/test_salud_api.py::test_la_especificacion_openapi_se_genera PASSED [ 60%]
tests/test_salud_api.py::test_una_ruta_inexistente_devuelve_el_formato_de_error_uniforme PASSED [ 61%]
tests/test_seguridad.py::test_no_se_puede_indicar_la_cuenta_de_origen_en_la_peticion PASSED [ 63%]
tests/test_seguridad.py::test_no_se_puede_consultar_una_operacion_ajena PASSED [ 64%]
tests/test_seguridad.py::test_el_historial_solo_muestra_movimientos_propios PASSED [ 65%]
tests/test_seguridad.py::test_el_registro_ignora_campos_que_no_le_corresponden PASSED [ 67%]
tests/test_seguridad.py::test_ninguna_respuesta_expone_el_hash_de_la_contrasena PASSED [ 68%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[0] PASSED   [ 69%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[-1] PASSED  [ 71%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[-10000] PASSED [ 72%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[100000001] PASSED [ 73%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[treinta] PASSED [ 75%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[30.5] PASSED [ 76%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[None] PASSED [ 77%]
tests/test_seguridad.py::test_importes_invalidos_se_rechazan[100000000000000000000] PASSED [ 78%]
tests/test_seguridad.py::test_un_importe_decimal_no_se_redondea_en_el_servidor PASSED [ 80%]
tests/test_seguridad.py::test_intentos_de_inyeccion_sql_en_el_alias[luis'; DROP TABLE accounts; --] PASSED [ 81%]
tests/test_seguridad.py::test_intentos_de_inyeccion_sql_en_el_alias[' OR '1'='1] PASSED [ 82%]
tests/test_seguridad.py::test_intentos_de_inyeccion_sql_en_el_alias[luis union select * from users] PASSED [ 84%]
tests/test_seguridad.py::test_ninguna_respuesta_de_error_expone_traza_interna PASSED [ 85%]
tests/test_seguridad.py::test_el_logging_redacta_los_campos_sensibles PASSED [ 86%]
tests/test_transferencias.py::test_prueba_a_transferencia_correcta PASSED [ 88%]
tests/test_transferencias.py::test_el_saldo_consultado_coincide_con_el_de_la_base PASSED [ 89%]
tests/test_transferencias.py::test_prueba_b_fondos_insuficientes PASSED  [ 90%]
tests/test_transferencias.py::test_no_se_puede_transferir_a_uno_mismo PASSED [ 92%]
tests/test_transferencias.py::test_destino_inexistente PASSED            [ 93%]
tests/test_transferencias.py::test_la_transferencia_exige_clave_de_idempotencia PASSED [ 94%]
tests/test_transferencias.py::test_el_historial_muestra_entradas_y_salidas PASSED [ 96%]
tests/test_transferencias.py::test_consulta_del_estado_de_una_operacion PASSED [ 97%]
tests/test_transferencias.py::test_el_concepto_se_limpia_de_caracteres_de_control PASSED [ 98%]
tests/test_transferencias.py::test_el_total_en_circulacion_no_cambia_con_las_transferencias PASSED [100%]
============================= 76 passed in 26.47s ==============================
```
