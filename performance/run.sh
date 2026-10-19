#!/usr/bin/env bash
#
# Ejecuta una carrera de carga reproducible y verifica el resultado EN LA BASE
# DE DATOS, no solo en las respuestas HTTP.
#
# Uso:
#   ./performance/run.sh <escenario> <estrategia> [usuarios] [segundos]
#
#   escenario   mixto | caliente | lectura
#   estrategia  pessimistic | serializable
#
# Ejemplo:
#   ./performance/run.sh caliente pessimistic 100 60
#
set -euo pipefail
cd "$(dirname "$0")/.."

ESCENARIO="${1:-mixto}"
ESTRATEGIA="${2:-pessimistic}"
USUARIOS="${3:-100}"
SEGUNDOS="${4:-60}"
ARRANQUE="${5:-20}"   # usuarios añadidos por segundo

ETIQUETA="${ESCENARIO}-${ESTRATEGIA}-${USUARIOS}u-${SEGUNDOS}s"
SALIDA="performance/results/${ETIQUETA}"
mkdir -p "$SALIDA"

PY="./.venv/bin/python"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.perf.yml"

echo "=============================================================="
echo " PayCore, carrera de carga"
echo "   escenario   : $ESCENARIO"
echo "   estrategia  : $ESTRATEGIA"
echo "   usuarios    : $USUARIOS  (arranque de ${ARRANQUE}/s)"
echo "   duracion    : ${SEGUNDOS}s"
echo "   resultados  : $SALIDA"
echo "=============================================================="

echo
echo "[1/6] Levantando la API en configuracion de medicion"
PAYCORE_CONCURRENCY_STRATEGY="$ESTRATEGIA" $COMPOSE up -d --force-recreate api >/dev/null 2>&1
for _ in $(seq 1 60); do
  curl -fsS http://localhost:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -s http://localhost:8000/health | tee "$SALIDA/health.json"; echo

echo
echo "[2/6] Dejando la base en un estado conocido"
$COMPOSE exec -T db psql -U paycore -d paycore -q -c \
  "TRUNCATE idempotency_keys, ledger_entries, transfers, accounts, users RESTART IDENTITY CASCADE;"

echo "[3/6] Creando cuentas de carga"
PAYCORE_DATABASE_URL="postgresql+psycopg://paycore:paycore@localhost:5434/paycore" \
PAYCORE_JWT_SECRET="dev-secret-solo-para-desarrollo-no-usar-en-produccion" \
PYTHONPATH=backend $PY performance/seed_perf.py 50

echo
echo "[4/6] Ejecutando Locust"
PAYCORE_ESCENARIO="$ESCENARIO" ./.venv/bin/locust \
  -f performance/locustfile.py \
  --headless \
  --host http://localhost:8000 \
  --users "$USUARIOS" \
  --spawn-rate "$ARRANQUE" \
  --run-time "${SEGUNDOS}s" \
  --csv "$SALIDA/locust" \
  --csv-full-history \
  --only-summary \
  2>&1 | tee "$SALIDA/locust.log" || true

# Locust termina con codigo 1 cuando hubo peticiones fallidas. Aqui eso no es
# un error del script: los fallos son precisamente parte de lo que se mide
# (en el escenario caliente con SERIALIZABLE casi todas lo son). Se continua a
# la verificacion, que es la que dice si el dinero quedo bien.

echo
echo "[5/6] Entorno de la medicion"
{
  echo "fecha=$(date -Iseconds)"
  echo "escenario=$ESCENARIO"
  echo "estrategia=$ESTRATEGIA"
  echo "usuarios=$USUARIOS"
  echo "segundos=$SEGUNDOS"
  echo "cpu=$(lscpu | awk -F: '/Model name/{gsub(/^ +/,"",$2); print $2; exit}')"
  echo "nucleos=$(nproc)"
  echo "ram=$(free -g | awk '/Mem:/{print $2"Gi"}')"
  echo "kernel=$(uname -r)"
  echo "api_workers=4"
  echo "postgres=$($COMPOSE exec -T db psql -U paycore -d paycore -tAc 'SHOW server_version')"
  echo "locust=$(./.venv/bin/locust --version 2>&1 | head -1)"
} | tee "$SALIDA/entorno.txt"

echo
echo "[6/6] Verificacion EN LA BASE DE DATOS"
echo "      Locust mide lo que responde la API. Esto comprueba que el dinero"
echo "      quedo correctamente registrado, que es otra cosa."
$COMPOSE exec -T db psql -U paycore -d paycore -P pager=off -c "
WITH cuadre AS (
  SELECT coalesce(sum(amount_cents), 0) AS suma_global FROM ledger_entries
), descuadres AS (
  SELECT count(*) AS cuentas_descuadradas FROM (
    SELECT a.id
      FROM accounts a
      LEFT JOIN ledger_entries l ON l.account_id = a.id
     GROUP BY a.id, a.balance_cents
    HAVING a.balance_cents <> coalesce(sum(l.amount_cents), 0)
  ) d
), negativos AS (
  SELECT count(*) AS saldos_negativos FROM accounts
   WHERE kind = 'user' AND balance_cents < 0
), movimientos AS (
  SELECT
    count(*) FILTER (WHERE status = 'completed') AS completadas,
    count(*) FILTER (WHERE status = 'rejected')  AS rechazadas
  FROM transfers
), asientos AS (
  SELECT count(*) AS total_asientos FROM ledger_entries
)
SELECT * FROM cuadre, descuadres, negativos, movimientos, asientos;
" | tee "$SALIDA/reconciliacion.txt"

echo
echo "Resultados en $SALIDA"
