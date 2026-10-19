#!/usr/bin/env bash
# Regenera docs/openapi.json a partir del código. El CI falla si divergen.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=backend python - <<'PY'
import json
import pathlib

from app.main import create_app

especificacion = create_app().openapi()
destino = pathlib.Path("docs/openapi.json")
destino.write_text(json.dumps(especificacion, indent=2, ensure_ascii=False) + "\n")
print(f"Escrito {destino}")
PY
