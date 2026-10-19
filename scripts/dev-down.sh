#!/usr/bin/env bash
# Detiene PayCore. Con --purge borra también el volumen de datos.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" = "--purge" ]; then
  docker compose down -v
  echo "Contenedores y volumen de datos eliminados."
else
  docker compose down
  echo "Contenedores detenidos. El volumen pgdata se conserva."
  echo "Para borrar también los datos: ./scripts/dev-down.sh --purge"
fi
