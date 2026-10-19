# ADR-0001. Monolito modular con dominio aislado

- **Estado:** aceptada
- **Fecha:** 2026-10-18
- **Contexto de decisión:** Fase 1, sección 4 de [research.md](../research.md)

## Contexto

PayCore lo desarrolla una sola persona y su operación central, la transferencia, debe ser atómica: debitar y acreditar ocurren juntos o no ocurren. Hay que elegir organización de código y de despliegue.

## Decisión

Un **monolito modular**: un despliegue, una base de datos, y módulos internos (`identity`, `accounts`, `ledger`, `transfers`, `idempotency`, `platform`, `api`) con la regla de que ningún módulo accede a las tablas de otro. El núcleo de dominio no importa FastAPI ni SQLAlchemy, al estilo de puertos y adaptadores, pero solo donde esa indirección se paga sola.

## Alternativas descartadas

- **Monolito tradicional en capas.** Funciona, pero acopla la lógica de transferencia a HTTP y al ORM, y no demuestra criterio de diseño.
- **Microservicios.** Separar cuentas y ledger en servicios con bases de datos distintas destruye la atomicidad y obliga a Saga o a commit en dos fases. Se cambiaría una garantía fuerte y gratuita por una débil y cara. Fowler, *MonolithFirst* (2015), sostiene que no se debe empezar un proyecto nuevo con microservicios aunque se prevea que será grande.
- **Arquitectura orientada a eventos como núcleo.** La transferencia debe ser síncrona y atómica. Los eventos encajan en lo que viene *después* (notificaciones, antifraude), no en la ruta del dinero.

## Consecuencias

**Positivas.** La atomicidad es un `COMMIT`. El dominio se prueba sin levantar HTTP. Las fronteras quedan documentadas y son el mapa de una extracción futura.

**Negativas.** La disciplina de frontera depende de revisión, no del compilador. Mitigación: una prueba de arquitectura que falla si un módulo importa los modelos de otro.

**Reversibilidad.** Alta. Los módulos con interfaz explícita son el punto de corte natural si alguna vez hiciera falta extraer un servicio.
