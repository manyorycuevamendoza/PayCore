/**
 * Conversión entre soles escritos por una persona y céntimos enteros.
 *
 * Deliberadamente SIN parseFloat. `parseFloat("30.10") * 100` da
 * 3009.9999999999995, y redondearlo funciona casi siempre, que en dinero no
 * es suficiente. Aquí se separa la cadena por el punto decimal y se opera con
 * enteros, igual que hace el backend (ver ADR-0003).
 */

export const CENTS_PER_UNIT = 100;

export class MoneyFormatError extends Error {}

export function parseSolesToCents(entrada: string): number {
  const limpio = entrada.trim().replace(",", ".");
  if (limpio === "") {
    throw new MoneyFormatError("Escribe un importe.");
  }
  if (!/^\d{1,9}(\.\d{0,2})?$/.test(limpio)) {
    throw new MoneyFormatError(
      "Usa solo dígitos y como mucho dos decimales, por ejemplo 30.50",
    );
  }

  const [enteros, decimales = ""] = limpio.split(".");
  const centimos = decimales.padEnd(2, "0");
  const total = Number(enteros) * CENTS_PER_UNIT + Number(centimos);

  if (!Number.isSafeInteger(total)) {
    throw new MoneyFormatError("El importe es demasiado grande.");
  }
  if (total <= 0) {
    throw new MoneyFormatError("El importe debe ser mayor que cero.");
  }
  return total;
}

/** Formatea céntimos para mostrar. No se usa para calcular nada. */
export function formatCents(cents: number): string {
  const signo = cents < 0 ? "-" : "";
  const absoluto = Math.abs(cents);
  const enteros = Math.trunc(absoluto / CENTS_PER_UNIT);
  const decimales = String(absoluto % CENTS_PER_UNIT).padStart(2, "0");
  const conSeparadores = enteros.toLocaleString("es-PE");
  return `${signo}S/ ${conSeparadores}.${decimales}`;
}

export function formatDateTime(iso: string): string {
  const fecha = new Date(iso);
  return new Intl.DateTimeFormat("es-PE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(fecha);
}
