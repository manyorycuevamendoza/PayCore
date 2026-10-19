# PayCore

> **Prototipo educativo.** Billetera digital con fondos **simulados** en soles peruanos (PEN). No se conecta a Yape, a Credicorp, a ninguna entidad bancaria ni a ninguna pasarela de pago. No mueve dinero real y no utiliza marcas ni identidades visuales de terceros.

Motor transaccional para una billetera digital simulada, construido para demostrar competencias en transacciones ACID, concurrencia, idempotencia, diseño de bases de datos, seguridad de APIs y medición de rendimiento.

**Autora:** Manyory Estefany Cueva Mendoza

## Estado actual

El proyecto está en construcción. **Backend terminado** (Fases 1 a 4, hitos H1 a H9) con **96 pruebas en verde**. Faltan el frontend, las pruebas de carga y el informe técnico.

Funciona hoy: registro y autenticación con Argon2id y JWT, consulta de cuenta y saldo, transferencia entre cuentas con ledger de doble entrada, rechazo por fondos insuficientes, control de concurrencia con dos estrategias comparables, idempotencia persistente, historial de movimientos y limitación de peticiones.

**Las seis pruebas del enunciado están hechas y verificadas en la base de datos**, no en las respuestas HTTP:

| | Escenario | Resultado |
|---|---|---|
| A | Ana S/100, Luis S/20, Ana envía S/30 | Ana S/70, Luis S/50, dos asientos que suman cero |
| B | Ana intenta S/200 teniendo S/100 | Rechazada, saldos intactos, cero asientos |
| C | Dos envíos con la misma clave de idempotencia | Una sola transferencia efectiva |
| D | 100 peticiones concurrentes de S/30 sobre S/100 | Exactamente 3 aprobadas, saldo final S/10 |
| E | Fallos antes y después del commit, y caída del proceso de base de datos | Atomicidad e idempotencia verificadas |
| F | Operar sobre cuentas ajenas e importes inválidos | 19 pruebas por riesgo del OWASP API Top 10 2023 |

Falta el frontend en React, las pruebas de carga con Locust y el informe en LaTeX.

### Limitaciones conocidas

Están declaradas por escrito en lugar de presentarse como lo que no son:

- **Un solo nodo de base de datos.** Sin alta disponibilidad ni replicación.
- **El rate limiting cuenta en memoria del proceso.** Con varios workers el límite efectivo se multiplica por el número de procesos. Ver [ADR-0009](docs/decisions/0009-rate-limiting.md).
- **JWT sin revocación inmediata.** Un token robado vale hasta que caduca; se mitiga con vida corta de 15 minutos.
- **Docker Compose no es un despliegue de producción.**

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

### Datos ficticios de prueba

```bash
./scripts/seed.sh
```

Crea tres personas (`ana`, `luis`, `rosa`) con saldo simulado y contraseña `PayCoreDemo2026`. El saldo no aparece de la nada: se acredita desde una cuenta de sistema que queda en negativo, de modo que el libro mayor sigue sumando exactamente cero. Para vaciar los datos sin tocar el esquema, `./scripts/reset-data.sh`.

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
