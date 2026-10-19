# Evidencia de ejecución: hito H10, interfaz web

18 de octubre de 2026. React 19.3.1, Vite 7.3.7, TypeScript 5.9.3 en modo
estricto con `exactOptionalPropertyTypes`.

## Recorrido real en el navegador

Hecho contra el stack levantado con `docker compose`, iniciando sesión como
Ana con los datos de `./scripts/seed.sh`:

1. **Acceso.** Login con `ana@ejemplo.pe`. Entra al panel.
2. **Panel.** Muestra saldo S/70.00 y el historial con la transferencia previa
   a Luis y la carga inicial desde `SYSTEM_FUNDING`.
3. **Transferencia.** S/12.50 a `rosa` con concepto "Cena del viernes". El
   saldo pasa a S/57.50, aparece la confirmación con el identificador de la
   operación y el historial se actualiza al momento.
4. **Fondos insuficientes.** Intento de S/999.00 teniendo S/57.50. El cliente
   avisa al escribir, pero **no bloquea el envío**: la decisión la toma el
   servidor, que responde 422, y la interfaz muestra "No se realizó la
   transferencia". El saldo no cambia.
5. **Móvil.** A 375 px de ancho el diseño pasa a una columna sin desbordes.

Las capturas de `docs/capturas/` las genera `node scripts/capturas.mjs`, que
repite ese mismo recorrido con Playwright sobre el Chrome del sistema. Tenerlo
como script evita que las imágenes del README se queden desfasadas.

## Un fallo de accesibilidad encontrado y corregido

La primera versión de la tarjeta de saldo usaba texto blanco sobre el color de
acento. En tema claro el acento es verde oscuro y funciona, pero en tema
oscuro el acento es verde claro y el contraste caía a **2,11:1**, muy por
debajo del 4,5:1 que exige WCAG 2.1 AA para texto normal.

Se invirtió a tinta oscura sobre el acento claro. Ratios medidos con la
fórmula de luminancia relativa de WCAG:

| Caso | Contraste | Veredicto |
|---|---|---|
| Oscuro: blanco sobre acento claro (antes) | 2,11:1 | insuficiente |
| Oscuro: tinta oscura sobre acento claro (ahora) | 8,01:1 | AA |
| Claro: blanco sobre acento oscuro | 6,20:1 | AA |

## Decisiones de la interfaz que se pueden defender

**Sin librería de componentes ni de estado.** Para una pantalla de acceso y un
panel, Material UI o Redux serían peso sin beneficio. El estado del servidor
cabe en `useState` y `useEffect`, y los estilos en una hoja CSS de 500 líneas
con variables.

**El importe se convierte a céntimos sin `parseFloat`.** `parseFloat("30.10") *
100` da `3009.9999999999995`. Redondear funciona casi siempre, y "casi
siempre" no es suficiente con dinero. El cliente separa la cadena por el punto
decimal y opera con enteros, igual que el backend (ADR-0003).

**La clave de idempotencia se conserva entre reintentos.** Se genera una por
intento de operación y se guarda en una referencia. Si la petición falla por
red, la interfaz no la descarta: muestra "Resultado no confirmado", cambia el
botón a "Reintentar envío" y reenvía **la misma clave**. Es el lado cliente de
lo que verifica la Prueba E.

**El frontend avisa pero no decide.** Cuando el importe supera el saldo, se
marca el campo en rojo, y aun así el botón sigue habilitado: la autoridad es
el servidor. Es deliberado, para que la validación del cliente sea una
comodidad y nunca la garantía.

**Franja de prototipo permanente.** No es descartable. Deja claro en todo
momento que los fondos son simulados y que no hay conexión con ninguna entidad
bancaria.
