# PayCore. Mediciones de rendimiento (Fase 7)

Todas las cifras de este documento proceden de ejecuciones reales cuyos CSV
están versionados en [performance/results/](../performance/results/). Los
gráficos los genera `performance/graficos.py` leyendo esos mismos CSV: no hay
ningún número escrito a mano. Si una carrera no existe, su barra no se dibuja.

## 1. Qué se mide y qué no

Locust mide **lo que responde la API**: cuántas peticiones por segundo atiende
y en cuánto tiempo. Eso no dice nada sobre si el dinero quedó bien registrado.
Un servicio que devolviera 201 a todo sin escribir nada daría unos números
magníficos aquí.

Por eso cada carrera termina con una **verificación contra PostgreSQL**
(`performance/run.sh`, paso 6) que comprueba sobre los datos:

- la suma global del ledger es exactamente cero,
- ninguna cuenta tiene el saldo materializado descuadrado respecto a sus asientos,
- ningún saldo de usuario es negativo,
- cuántas transferencias quedaron realmente escritas.

Esa última cifra da la métrica que de verdad importa, **transferencias
confirmadas por segundo**, que no coincide con las peticiones por segundo en
cuanto hay fallos. La tabla de la sección 4 muestra las dos juntas, y la
diferencia entre ambas es el resultado más interesante de toda la fase.

## 2. Entorno

Todas las carreras se ejecutaron en la misma máquina, en la misma sesión y con
la misma configuración. Los datos los recoge el propio script en
`entorno.txt` dentro de cada carpeta de resultados.

```
fecha=2026-10-18T20:55:22-05:00
escenario=caliente
estrategia=pessimistic
usuarios=100
segundos=60
cpu=AMD Ryzen 7 5800H with Radeon Graphics
nucleos=16
ram=15Gi
kernel=7.0.0-34-generic
api_workers=4
postgres=16.10
locust=locust 2.46.7 from /home/manyory/Documentos/PayCore/.venv/lib/python3.12/site-packages/locust (Python 3.12.3)
```

La API se levanta con [docker-compose.perf.yml](../docker-compose.perf.yml),
que difiere del entorno de desarrollo en cuatro cosas, todas deliberadas:

| Cambio | Motivo |
|---|---|
| Sin `--reload` ni código montado | El observador de ficheros introduce ruido que no existiría en un despliegue real |
| 4 workers de Uvicorn | Así hay concurrencia **real entre procesos** contra PostgreSQL, que es justo lo que el proyecto afirma garantizar. Con un solo proceso la medición sería más amable y menos honesta |
| Rate limiting apagado | Con el limitador activo mediríamos el limitador y no el motor transaccional. Además su contador es por proceso (ADR-0009), así que con cuatro workers ni siquiera sería coherente |
| Log a nivel WARNING | Escribir una línea JSON por petición a stdout distorsiona la latencia bajo carga |

## 3. Escenarios

Los tres están en [performance/locustfile.py](../performance/locustfile.py) y
se eligen con `PAYCORE_ESCENARIO`.

| Escenario | Qué hace | Para qué sirve |
|---|---|---|
| `lectura` | Solo saldo e historial | Línea base: cuánto cuesta la infraestructura sin trabajo transaccional |
| `mixto` | Lecturas y transferencias entre 50 cuentas al azar | Contención baja, reparto más realista |
| `caliente` | Todas las transferencias salen de **la misma** cuenta | Contención máxima sobre una fila: el peor caso para el control de concurrencia |

Cada carrera: 100 usuarios simulados, arranque de 20 por segundo, 60 segundos
de duración, importe fijo de S/1,00 simulado y una clave de idempotencia nueva
por petición. Reproducible con:

```bash
./performance/run.sh caliente pessimistic 100 60
```

## 4. Resultados

| Escenario | Estrategia | Peticiones | req/s | transf. confirmadas/s | p50 | p95 | p99 | Máx. | Fallos |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Solo lectura | `pessimistic` | 4509 | 76.3 | n/a | 580 ms | 780 ms | 840 ms | 1100 ms | 0.00 % |
| Contención baja | `pessimistic` | 4955 | 83.8 | 84.5 | 590 ms | 770 ms | 990 ms | 1264 ms | 0.00 % |
| Contención baja | `serializable` | 3546 | 60.0 | 43.3 | 820 ms | 1300 ms | 1400 ms | 1599 ms | 27.35 % |
| Contención máxima | `pessimistic` | 8683 | 147.0 | 148.3 | 600 ms | 900 ms | 1100 ms | 1478 ms | 0.00 % |
| Contención máxima | `serializable` | 3729 | 63.1 | 10.4 | 1500 ms | 1900 ms | 2200 ms | 2472 ms | 83.72 % |
