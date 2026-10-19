# ADR-0003. Representar el dinero como enteros de céntimos (`BIGINT`)

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

Hay que elegir la representación de los importes en el dominio, en la base de datos y en la API. El punto flotante binario no representa exactamente 0.01, lo que produce errores de redondeo acumulativos (Goldberg, 1991). La propia documentación de PostgreSQL advierte de que "los números en punto flotante no deberían usarse para manejar dinero".

## Decisión

Los importes se almacenan y se operan como **enteros de céntimos en `BIGINT`**, en el dominio y en el esquema. La conversión a decimal con dos cifras ocurre únicamente en la serialización de la API (`amount_display`) y en la interfaz.

## Alternativas descartadas

- **`NUMERIC(18,2)`.** Exacto y legible, pero la aritmética es más lenta y existe riesgo de deriva de escala si alguna operación produce más decimales. Es una opción defendible; se descarta por preferir que la invariante "la suma de los asientos es exactamente cero" sea cierta por construcción en aritmética entera.
- **`MONEY`.** Precisión fraccional dependiente de `lc_monetary`, dependiente de configuración regional.
- **`FLOAT`/`DOUBLE`.** Descartado por las dos fuentes citadas.

## Consecuencias

**Positivas.** Comparaciones y sumas exactas. La invariante global de cuadre se verifica con una suma de enteros.

**Negativas.** No admite fracciones de céntimo, lo que impediría calcular intereses o comisiones prorrateadas sin una decisión adicional de redondeo. PayCore no las tiene. Si se añadieran, la vía sería `NUMERIC` con política de redondeo explícita, no punto flotante.

**Obligación derivada.** Toda entrada de la API valida que `amount_cents` sea entero y estrictamente positivo; no se acepta un decimal que haya que redondear en el servidor.
