# ADR-0007. JWT de vida corta y Argon2id para contraseñas

- **Estado:** aceptada
- **Fecha:** 2026-10-18

## Contexto

PayCore necesita identificar al autor de cada operación, porque la cuenta origen de una transferencia se deriva del sujeto autenticado y nunca del cuerpo de la petición. Esa es la mitigación de API1:2023 Broken Object Level Authorization, el primer riesgo del OWASP API Security Top 10 2023.

## Decisión

- **Contraseñas:** Argon2id con la configuración mínima que recomienda OWASP: 19 MiB de memoria, 2 iteraciones, 1 grado de paralelismo. Implementación `argon2-cffi`.
- **Sesión:** JWT firmado con HS256, vida corta (15 minutos previstos), secreto desde variable de entorno y obligatorio en despliegue.
- La cuenta origen se obtiene siempre del `sub` del token.
- Los recursos ajenos devuelven **404**, no 403, para no confirmar su existencia.

## Alternativas descartadas

- **bcrypt.** OWASP lo recomienda para sistemas heredados, con un factor de trabajo mínimo de 10, y advierte de su límite de 72 bytes de entrada. Argon2id es la primera recomendación.
- **Sesión en base de datos con cookie.** Permitiría revocación inmediata, a cambio de una lectura por petición. Es la opción correcta si la revocación fuera un requisito; aquí se documenta como mejora y no como necesidad del MVP.

## Consecuencias

**Positivas.** Parámetros de hashing citables de una fuente, sin elección arbitraria. Sin estado de sesión en el servidor.

**Negativas.** Un token robado es válido hasta que expira. Se mitiga con vida corta y se declara como limitación en [architecture.md](../architecture.md).
