import { MoneyFormatError, parseSolesToCents } from "./money";

export function validarEnvio(destino: string, importe: string, aliasPropio: string, saldoCents: number | null) {
  const alias = destino.trim().toLowerCase();
  let centimos: number | null = null;
  let errorImporte: string | null = null;
  if (importe.trim()) {
    try { centimos = parseSolesToCents(importe); }
    catch (causa) {
      errorImporte = causa instanceof MoneyFormatError ? causa.message : "Importe inválido.";
    }
  }
  const errorDestino = alias === aliasPropio.toLowerCase()
    ? "No puedes enviar a tu propia cuenta. Usa el alias de otra persona."
    : alias && !/^[a-z0-9][a-z0-9._-]{2,31}$/.test(alias)
      ? "Usa entre 3 y 32 caracteres: letras, números, punto, guion o guion bajo."
      : null;
  const sinSaldo = centimos !== null && saldoCents !== null && centimos > saldoCents;
  const motivo = !alias ? "Escribe el alias de quien recibirá el envío."
    : errorDestino ?? (!importe.trim() ? "Escribe cuánto quieres enviar."
      : errorImporte ?? (saldoCents === null ? "Espera a que se cargue tu saldo."
        : sinSaldo ? "Reduce el importe: supera tu saldo disponible." : null));
  return { alias, centimos, errorImporte, errorDestino, sinSaldo, motivo };
}
