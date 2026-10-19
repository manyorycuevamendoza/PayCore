# ADR-0009. Limitación de peticiones en memoria del proceso

- **Estado:** aceptada, con una limitación declarada que condiciona su validez
- **Fecha:** 2026-10-18

## Contexto

API4:2023 (Unrestricted Resource Consumption) y API6:2023 (Unrestricted Access to Sensitive Business Flows) del OWASP API Security Top 10 piden acotar el consumo de recursos y el acceso a los flujos de negocio sensibles. En PayCore eso son dos endpoints: el login, por relleno de credenciales, y la transferencia, por abuso del flujo que mueve dinero.

La regla de admisión del proyecto prohíbe añadir Redis sin un requisito que lo justifique. Un limitador compartido lo justificaría, pero solo cuando haya más de un proceso.

## Decisión

**Cubo de fichas (token bucket) en memoria del proceso**, con una clave distinta por endpoint:

| Endpoint | Clave | Ráfaga | Ritmo sostenido |
|---|---|---|---|
| `POST /auth/login` y `POST /auth/register` | dirección de origen | 5 | 10 por minuto |
| `POST /transfers` | usuario autenticado | 10 | 60 por minuto |

Al cortar se responde **429** con cabecera `Retry-After`. Además, un middleware rechaza con **413** cualquier cuerpo que declare más de 16 KiB.

### Por qué cubo de fichas y no ventana fija

La ventana fija permite el doble del límite a caballo entre dos ventanas: cinco peticiones al final de una y cinco al principio de la siguiente son diez en un instante. El cubo de fichas no tiene ese borde y además separa de forma explícita la ráfaga tolerada del ritmo sostenido.

### Por qué claves distintas

En el login todavía no sabemos quién pide, así que la única clave disponible es el origen. En la transferencia sí lo sabemos, y limitar por IP castigaría a toda una red compartida (una universidad, una oficina) por el abuso de una sola persona.

**No se confía en `X-Forwarded-For`.** Es trivial de falsificar salvo que exista un proxy de confianza que la reescriba, y PayCore no tiene ninguno. Si algún día se despliega detrás de uno, hay que tratarla explícitamente en lugar de aceptarla por defecto.

### Qué no se limita

Las lecturas (saldo, cuenta, historial) no están limitadas. Son baratas, están paginadas y limitarlas molestaría al usuario sin mitigar nada relevante. El tope de recursos en esa parte lo pone la paginación obligatoria.

## Limitación que invalida esta decisión en cuanto cambie el despliegue

**El contador vive en memoria del proceso.** Con varios workers de Uvicorn o varias réplicas del contenedor, el límite efectivo se multiplica por el número de procesos: con cuatro workers, la ráfaga real del login es 20 y no 5.

Esto se declara aquí, en el código y en el README en lugar de presentarse como una defensa que no es. Mientras el despliegue sea de un proceso, el límite es el que dice la tabla. En cuanto deje de serlo, deja de serlo.

**Condición de reingreso de Redis:** pasar a más de un proceso de API. En ese momento el contador debe ser compartido, y Redis es la pieza adecuada, porque aquí sí resuelve un problema real y no rompe ninguna garantía transaccional (a diferencia de usarlo para idempotencia, descartado en ADR-0006).

## Alternativas descartadas

- **Contador en PostgreSQL.** Sería correcto entre procesos, pero añade una escritura por petición al mismo motor que debe atender las transferencias, y contaminaría las mediciones de la Fase 7 mezclando el coste del limitador con el del trabajo real.
- **Limitar en un proxy inverso (nginx, Traefik).** Es donde suele vivir esto en producción, y sería la opción correcta en un despliegue real. Se descarta porque desplazaría la lógica fuera del repositorio y dejaría de ser demostrable con una prueba automatizada.
- **No limitar nada.** Dejaría API4:2023 y API6:2023 sin ninguna mitigación.

## Consecuencias

Se añade una dependencia cero: son unas setenta líneas de Python sin librerías externas. El limitador purga los cubos inactivos, porque un diccionario que crece con cada IP nueva sería exactamente el problema de consumo de recursos que pretende evitar.

Las pruebas lo verifican en dos niveles: el cubo como unidad con reloj inyectado (determinista, sin esperas reales) y los endpoints de extremo a extremo, comprobando además que una petición limitada **no mueve dinero**.
