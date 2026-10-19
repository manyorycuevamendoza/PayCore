/**
 * Genera las capturas del README recorriendo la aplicación de verdad.
 *
 * Son capturas reales: se abre la interfaz, se inicia sesión y se hacen las
 * operaciones. Tenerlo como script y no a mano evita que las imágenes del
 * README se queden desfasadas respecto al código.
 *
 * Requisitos: docker compose levantado, ./scripts/seed.sh ejecutado y Chrome
 * instalado en el sistema (o `npx playwright install chromium`).
 *
 * Uso:  node scripts/capturas.mjs
 */

import { mkdir } from "node:fs/promises";
import { chromium } from "../frontend/node_modules/playwright/index.mjs";

const WEB = process.env.PAYCORE_WEB_URL ?? "http://localhost:5173";
const DESTINO = new URL("../docs/capturas/", import.meta.url).pathname;

const CUENTA = { email: "ana@ejemplo.pe", password: "PayCoreDemo2026" };

async function iniciarSesion(page) {
  await page.goto(WEB, { waitUntil: "networkidle" });
  await page.getByLabel("Correo").fill(CUENTA.email);
  await page.getByLabel("Contraseña").fill(CUENTA.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByText("Saldo disponible").waitFor();
}

async function capturar(page, nombre) {
  const ruta = `${DESTINO}${nombre}.png`;
  await page.screenshot({ path: ruta });
  console.log(`  ${nombre}.png`);
}

async function main() {
  await mkdir(DESTINO, { recursive: true });
  // Se usa el Chrome del sistema en lugar del Chromium que descarga
  // Playwright: evita bajar 170 MB solo para generar unas capturas.
  // Si no hubiera Chrome instalado, se recurre al navegador de Playwright.
  let navegador;
  try {
    navegador = await chromium.launch({ channel: "chrome" });
  } catch {
    navegador = await chromium.launch();
  }

  console.log("Capturas generadas en docs/capturas/:");

  for (const tema of ["light", "dark"]) {
    const contexto = await navegador.newContext({
      viewport: { width: 1280, height: 860 },
      colorScheme: tema,
      // Escala 1: 1280 px de ancho basta para el README y mantiene los
      // PNG por debajo de 150 KB. Con escala 2 pesaban 400 KB cada uno.
      deviceScaleFactor: 1,
      locale: "es-PE",
      timezoneId: "America/Lima",
    });
    const page = await contexto.newPage();

    // 1. Acceso
    await page.goto(WEB, { waitUntil: "networkidle" });
    await capturar(page, `01-acceso-${tema}`);

    // 2. Panel con saldo e historial
    await iniciarSesion(page);
    await page.waitForTimeout(400);
    await capturar(page, `02-panel-${tema}`);

    // 3. Transferencia completada
    const sufijo = Math.random().toString(36).slice(2, 6);
    await page.getByLabel("Alias de destino").fill("luis");
    await page.getByLabel("Importe en soles simulados").fill("4.25");
    await page.getByLabel(/Concepto/).fill(`Café ${sufijo}`);
    await page.getByRole("button", { name: "Enviar" }).click();
    await page.getByText("Transferencia completada").waitFor();
    await page.waitForTimeout(400);
    await capturar(page, `03-transferencia-completada-${tema}`);

    // 4. Rechazo por fondos insuficientes, decidido por el servidor
    await page.getByLabel("Alias de destino").fill("luis");
    await page.getByLabel("Importe en soles simulados").fill("99999.00");
    await page.getByRole("button", { name: "Enviar" }).click();
    await page.getByText("No se realizó la transferencia").waitFor();
    await page.waitForTimeout(400);
    await capturar(page, `04-fondos-insuficientes-${tema}`);

    await contexto.close();
  }

  // 5. Móvil
  const movil = await navegador.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    colorScheme: "light",
    locale: "es-PE",
    timezoneId: "America/Lima",
  });
  const pageMovil = await movil.newPage();
  await iniciarSesion(pageMovil);
  await pageMovil.waitForTimeout(400);
  await capturar(pageMovil, "05-movil");
  await movil.close();

  await navegador.close();
}

main().catch((error) => {
  console.error("Fallo al generar las capturas:", error.message);
  console.error(
    "Comprueba que docker compose está levantado y que ./scripts/seed.sh se ejecutó.",
  );
  process.exit(1);
});
