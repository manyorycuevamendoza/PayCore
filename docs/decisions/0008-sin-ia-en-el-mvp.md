# ADR-0008. Sin IA en el MVP, y límite duro sobre decisiones de dinero

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

Añadir aprendizaje automático o modelos fundacionales a un proyecto de portafolio es tentador. La pregunta correcta es qué problema resolverían con los datos que realmente existen.

## Decisión

1. **El MVP no incluye ningún componente de IA.**
2. Se planifica para una Fase 2 un servicio de riesgo basado en **reglas deterministas** (velocidad de envío, importe atípico frente al historial propio, receptor nuevo), con detección de anomalías no supervisada como experimento opcional y explícitamente etiquetado como entrenado sobre datos sintéticos.
3. **Límite permanente:** ningún modelo generativo ni estadístico aprueba, rechaza ni modifica una transferencia o un saldo. El motor de riesgo solo puede adjuntar una **marca de revisión**. Las decisiones sobre el dinero las toman reglas deterministas y restricciones de base de datos.

## Justificación

- Un clasificador supervisado de fraude necesitaría transacciones reales etiquetadas, que no existen y no se pueden fabricar sin falsear el resultado. Reportar métricas de un modelo entrenado sobre datos inventados sería exactamente el tipo de cifra que este proyecto se ha comprometido a no producir.
- RAG y una base de datos vectorial serían infraestructura sin un corpus que consultar.
- Sculley et al., *Hidden Technical Debt in Machine Learning Systems* (NIPS 2015, pp. 2503-2511), documentan que el código de modelo es una fracción pequeña de un sistema de ML y que el resto es deuda de mantenimiento continua. Incurrir en esa deuda sin datos ni evaluación creíble no aporta nada demostrable.
- Un sistema no determinista en la ruta crítica del dinero no es auditable. Poder explicar por qué no se puso es más valioso en una entrevista técnica que haber conectado un modelo.

## Consecuencias

El proyecto renuncia a una palabra de moda en el README a cambio de poder defender una decisión de diseño. La condición de reingreso está escrita: datos reales etiquetados y un protocolo de evaluación, para el componente de riesgo, y nunca para la autorización.
