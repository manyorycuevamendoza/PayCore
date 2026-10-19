# Evidencia de ejecución: hito H9

Limitación de peticiones y tope de tamaño de cuerpo. Ejecutado el 18 de
octubre de 2026 contra el stack levantado con `docker compose`.

Mitiga API4:2023 (Unrestricted Resource Consumption) y API6:2023 en el caso de
la transferencia. Decisión y limitaciones en
[ADR-0009](../decisions/0009-rate-limiting.md).

## El límite del login funciona en el stack real

Ráfaga configurada: 5. Siete intentos de login con contraseña incorrecta desde
el mismo origen:

```
intento 1 -> 401
intento 2 -> 401
intento 3 -> 401
intento 4 -> 401
intento 5 -> 401
intento 6 -> 429
intento 7 -> 429
```

La respuesta 429 le dice al cliente cuándo reintentar:

```
HTTP/1.1 429 Too Many Requests
retry-after: 6
```

## Tope de tamaño de cuerpo

Un registro con 40 000 caracteres en el campo de contraseña:

```
codigo: 413
```

El cuerpo se rechaza por `Content-Length` antes de intentar parsearlo, así que
el coste del ataque recae en quien lo lanza y no en el servidor.

## Lo que esta evidencia NO demuestra

El contador vive en memoria del proceso. Esta prueba se ejecutó contra **un**
proceso de Uvicorn, y por eso los números salen exactos. Con cuatro workers,
la ráfaga efectiva del login sería 20 y no 5. Está declarado en ADR-0009 y en
el README, y es la condición escrita de reingreso de Redis.

## Suite completa

96 pruebas en verde. Las del limitador están en dos niveles: el cubo de fichas
como unidad con reloj inyectado (determinista, sin esperas reales) y los
endpoints de extremo a extremo, incluida una que comprueba que **una petición
limitada no mueve dinero**.

```
tests/test_rate_limit.py::test_el_cubo_permite_la_rafaga_y_despues_corta PASSED [ 55%]
tests/test_rate_limit.py::test_el_cubo_se_rellena_con_el_tiempo PASSED   [ 56%]
tests/test_rate_limit.py::test_el_cubo_dice_cuanto_falta_para_la_siguiente_ficha PASSED [ 57%]
tests/test_rate_limit.py::test_el_limitador_no_acumula_claves_sin_limite PASSED [ 58%]
tests/test_rate_limit.py::test_cada_clave_tiene_su_propio_cubo PASSED    [ 59%]
tests/test_rate_limit.py::test_el_login_corta_tras_la_rafaga PASSED      [ 60%]
tests/test_rate_limit.py::test_la_transferencia_se_limita_por_usuario_y_no_por_origen PASSED [ 61%]
tests/test_rate_limit.py::test_una_peticion_limitada_no_mueve_dinero PASSED [ 62%]
tests/test_rate_limit.py::test_la_consulta_de_saldo_no_esta_limitada PASSED [ 63%]
tests/test_rate_limit.py::test_un_cuerpo_desmesurado_se_rechaza_con_413 PASSED [ 64%]
tests/test_salud_api.py::test_health_responde_ok PASSED                  [ 65%]
tests/test_salud_api.py::test_toda_respuesta_lleva_identificador_de_correlacion PASSED [ 66%]
tests/test_salud_api.py::test_se_respeta_el_identificador_de_correlacion_del_cliente PASSED [ 67%]
tests/test_salud_api.py::test_la_especificacion_openapi_se_genera PASSED [ 68%]
tests/test_salud_api.py::test_una_ruta_inexistente_devuelve_el_formato_de_error_uniforme PASSED [ 69%]
tests/test_seguridad.py::test_no_se_puede_indicar_la_cuenta_de_origen_en_la_peticion PASSED [ 70%]
tests/test_seguridad.py::test_no_se_puede_consultar_una_operacion_ajena PASSED [ 71%]
tests/test_seguridad.py::test_el_historial_solo_muestra_movimientos_propios PASSED [ 72%]
tests/test_seguridad.py::test_el_registro_ignora_campos_que_no_le_corresponden PASSED [ 73%]
tests/test_seguridad.py::test_ninguna_respuesta_expone_el_hash_de_la_contrasena PASSED [ 75%]
...
============================= 96 passed in 15.44s ==============================
```
