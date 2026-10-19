#!/usr/bin/env bash
# Carga los datos ficticios dentro del contenedor de la API.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T -e PYTHONPATH=/srv api python scripts/seed.py
