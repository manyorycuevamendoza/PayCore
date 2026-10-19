#!/usr/bin/env bash
# Limpieza de datos: vacía las tablas y deja el esquema intacto.
# Se usa TRUNCATE y no DELETE porque el ledger es de solo inserción.
set -euo pipefail
cd "$(dirname "$0")/.."

read -r -p "Esto borra TODOS los datos de PayCore. ¿Continuar? [s/N] " respuesta
if [ "${respuesta,,}" != "s" ]; then
  echo "Cancelado."
  exit 0
fi

docker compose exec -T db psql -U "${POSTGRES_USER:-paycore}" -d "${POSTGRES_DB:-paycore}" -c \
  "TRUNCATE idempotency_keys, ledger_entries, transfers, accounts, users RESTART IDENTITY CASCADE;"
echo "Datos eliminados. El esquema y las migraciones se conservan."
