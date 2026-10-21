# Aplicación de los principios de Norman a PayCore

Fecha: 21 de octubre de 2026.

Tarea: una persona usa su billetera de prueba, también desde móvil, para enviar
fondos simulados y entender qué ocurrió. PayCore es un proyecto de portafolio.

Esta revisión procede de inspeccionar el código. Las dificultades de comprensión
son hipótesis; todavía no se ha observado a personas usando esta versión.
Se consultaron las guías locales `Biblioteca/Metodos/Diseno/aplicar-norman.md`
y `principios-de-norman.md`. Las decisiones siguientes son una aplicación propia.

| Hallazgo en el código anterior | Cambio | Principios relacionados |
|---|---|---|
| Enviar ejecutaba la operación directamente | Completar → revisar → confirmar, con alias, importe, concepto y saldo previsto; opción de volver y corregir | Modelo conceptual, mapeo y prevención del error mediante restricciones |
| Un importe superior al saldo mostraba aviso, pero permitía enviar | Bloquear la revisión y explicar cómo corregir el importe | Restricciones y feedback |
| Tras perder la conexión podían cambiarse los campos conservando la clave anterior | Conservar juntos cuerpo y clave; mostrar el resumen y ofrecer reintentar la misma operación | Restricciones, modelo conceptual y feedback |
| Cualquier respuesta de transferencia se anunciaba como completada | Mostrar éxito solo para `completed`; distinguir `pending` y `rejected` | Feedback |
| El botón deshabilitado no siempre explicaba qué faltaba | Ayuda persistente debajo del botón, vinculada con `aria-describedby` | Significantes y descubribilidad |
| El alias propio aparecía solo en la barra | Mostrarlo junto al saldo como alias para recibir | Descubribilidad y mapeo |
| El historial decía únicamente «De» o «A» | Usar «Recibido de» y «Enviado a», además de signos e iconos | Significantes |
| Formularios de acceso desactivaban validaciones nativas | Restaurar validación de correo, campos obligatorios y contraseña; bloquear cambios mientras se envía | Restricciones |

Se conservan la paleta, los temas claro y oscuro y las operaciones del servidor.
La revisión previa se eligió frente a un envío inmediato porque permite comprobar
un error de destinatario antes de ejecutar una acción sin opción de deshacer.
Para resultados inciertos se eligió bloquear la edición frente a permitir un
nuevo envío: primero debe resolverse la operación anterior.

## Criterios y comprobación técnica

Criterios definidos para la implementación:

- No se puede pasar a revisión con alias inválido o propio, importe inválido,
  saldo sin cargar o importe superior al saldo mostrado.
- Revisar no hace ninguna petición de transferencia; confirmar sí.
- El reintento conserva el mismo cuerpo y la misma clave.
- Un resultado pendiente no se anuncia como éxito.
- Las acciones tienen controles nativos de teclado; el foco pasa al resumen
  y al comprobante, y vuelve al destinatario al elegir corregir.

Comprobación realizada:

- `docker compose exec -T web npm test`: cuatro pruebas automatizadas de
  validación aprobadas, incluyendo saldo exacto, exceso de saldo, alias propio,
  datos incompletos y decimales con punto o coma.
- `docker compose exec -T web npm run build`: TypeScript y compilación aprobados.
- La interfaz responde HTTP 200 en `http://localhost:5173`.
- La conservación de la operación, las ramas de respuesta y el manejo de foco
  se revisaron en el código; no tienen una prueba automatizada de interacción.

## Evaluación pendiente

No había un navegador conectado disponible. No se ha comprobado visualmente el
resultado ni realizado pruebas de interacción con teclado o lector de pantalla.
Las pruebas de validación y la compilación no demuestran usabilidad.

Próxima evaluación: pedir a personas destinatarias «envía S/30 simulados a Luis»
sin explicar la secuencia, y comprobar si encuentran el alias, comprenden la
revisión y reconocen el resultado. Repetir con importe excesivo y conexión
interrumpida; comprobar que pueden corregir y que interpretan la incertidumbre.
Registrar dispositivo, ayuda ofrecida, finalización y errores, sin atribuir una
mejora medida antes de obtener esos resultados.

Límite existente: la operación pendiente vive en memoria del componente.
Recargar la página o cerrar sesión pierde ese contexto. La recuperación tras
recarga necesita un diseño adicional de persistencia y consulta de estado.
