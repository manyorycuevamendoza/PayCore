# PayCore

> **Prototipo educativo.** Billetera digital con fondos **simulados** en soles peruanos (PEN). No se conecta a Yape, a Credicorp, a ninguna entidad bancaria ni a ninguna pasarela de pago. No mueve dinero real y no utiliza marcas ni identidades visuales de terceros.

Motor transaccional para una billetera digital simulada, construido para demostrar competencias en transacciones ACID, concurrencia, idempotencia, diseño de bases de datos, seguridad de APIs y medición de rendimiento.

**Autora:** Manyory Estefany Cueva Mendoza

## Estado actual

El proyecto está en construcción. Fases 1, 2 y 3 completadas (investigación, justificación del stack y diseño). La Fase 4 está en curso: hitos H1 (esqueleto ejecutable) y H2 (esquema e invariantes en el motor) terminados y verificados, con 24 pruebas en verde.

### Levantarlo

```bash
./scripts/dev-up.sh
```

Deja la API en `http://localhost:8000`, la documentación interactiva en `http://localhost:8000/api/v1/docs` y PostgreSQL en el puerto 5434 del host. Para detenerlo, `./scripts/dev-down.sh` (añade `--purge` para borrar también los datos).

### Pruebas

```bash
python -m venv .venv && ./.venv/bin/pip install -r backend/requirements-dev.txt
./.venv/bin/python -m pytest -v
```

Las pruebas corren contra un PostgreSQL real, no contra SQLite: lo que se verifica son garantías del motor (restricciones `CHECK`, triggers, bloqueos y niveles de aislamiento) que otro motor no reproduce. Requieren el contenedor levantado.

Este README se reescribirá en la Fase 9 con funcionalidades implementadas, capturas reales, comandos verificados y resultados medidos. Mientras tanto, la documentación útil es:

| Documento | Contenido |
|---|---|
| [docs/research.md](docs/research.md) | Investigación con fuentes verificadas: integridad transaccional, concurrencia, idempotencia, arquitectura, seguridad e IA |
| [docs/stack.md](docs/stack.md) | Matriz de decisiones tecnológicas y ficha de cada tecnología |
| [docs/architecture.md](docs/architecture.md) | Diseño funcional, modelo de datos, invariantes, diagramas y contrato de la API |
| [docs/decisions/](docs/decisions/) | Ocho ADR con las decisiones y sus alternativas descartadas |
| [docs/plan.md](docs/plan.md) | Plan de construcción con criterios de aceptación por hito |
| [docs/evidence/](docs/evidence/) | Evidencia de ejecución real de las pruebas |

## Licencia

MIT. Ver [LICENSE](LICENSE).
