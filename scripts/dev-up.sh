#!/usr/bin/env bash
# Levanta PayCore desde cero y espera a que la API responda.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env a partir de .env.example"
fi

docker compose up -d --build

echo -n "Esperando a la API"
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${API_PORT:-8000}/health" >/dev/null 2>&1; then
    echo " listo"
    curl -s "http://localhost:${API_PORT:-8000}/health"
    echo
    echo "Documentación interactiva: http://localhost:${API_PORT:-8000}/api/v1/docs"
    exit 0
  fi
  echo -n "."
  sleep 2
done

echo
echo "La API no respondió a tiempo. Registro reciente:" >&2
docker compose logs --tail 50 api >&2
exit 1
