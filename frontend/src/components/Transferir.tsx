import { useRef, useState } from "react";
import { ApiError, NetworkError, api, nuevaClaveIdempotencia } from "../api/client";
import { MoneyFormatError, formatCents, parseSolesToCents } from "../api/money";
import type { TransferResponse } from "../api/types";
import { Aviso } from "./Aviso";
import { Cargando } from "./Cargando";

type Estado =
  | { tipo: "inactivo" }
  | { tipo: "enviando" }
  | { tipo: "hecho"; transferencia: TransferResponse }
  | { tipo: "rechazado"; mensaje: string; detalle?: string | undefined }
  | { tipo: "incierto"; mensaje: string };

export function Transferir({
  token,
  saldoCents,
  aliasPropio,
  onCompletada,
}: {
  token: string;
  saldoCents: number | null;
  aliasPropio: string;
  onCompletada: () => void;
}) {
  const [destino, setDestino] = useState("");
  const [importe, setImporte] = useState("");
  const [concepto, setConcepto] = useState("");
  const [estado, setEstado] = useState<Estado>({ tipo: "inactivo" });

  /**
   * La clave de idempotencia se genera una vez por intento de operación y se
   * CONSERVA entre reintentos. Si la respuesta se pierde y la persona vuelve
   * a pulsar, se reenvía la misma clave y el servidor reproduce la respuesta
   * original en lugar de mover el dinero por segunda vez.
   */
  const claveRef = useRef<string | null>(null);

  let importeCents: number | null = null;
  let errorImporte: string | null = null;
  if (importe.trim() !== "") {
    try {
      importeCents = parseSolesToCents(importe);
    } catch (causa) {
      errorImporte =
        causa instanceof MoneyFormatError ? causa.message : "Importe inválido.";
    }
  }

  const sinSaldo =
    importeCents !== null && saldoCents !== null && importeCents > saldoCents;
  const aSiMismo = destino.trim().toLowerCase() === aliasPropio;
  const puedeEnviar =
    importeCents !== null &&
    destino.trim().length >= 3 &&
    !aSiMismo &&
    estado.tipo !== "enviando";

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (importeCents === null) return;

    if (claveRef.current === null) claveRef.current = nuevaClaveIdempotencia();
    setEstado({ tipo: "enviando" });

    try {
      const transferencia = await api.transferir(token, claveRef.current, {
        destination_alias: destino.trim().toLowerCase(),
        amount_cents: importeCents,
        concept: concepto.trim() === "" ? null : concepto.trim(),
      });
      claveRef.current = null;
      setEstado({ tipo: "hecho", transferencia });
      setDestino("");
      setImporte("");
      setConcepto("");
      onCompletada();
    } catch (causa) {
      if (causa instanceof NetworkError) {
        // No sabemos si llegó. La clave se conserva a propósito: volver a
        // pulsar reenvía la misma y no puede duplicar el pago.
        setEstado({
          tipo: "incierto",
          mensaje:
            "No hemos podido confirmar la operación. Vuelve a pulsar Enviar: " +
            "se reintentará de forma segura y no se cobrará dos veces.",
        });
        return;
      }
      if (causa instanceof ApiError) {
        if (causa.code === "insufficient_funds") {
          claveRef.current = null;
          setEstado({
            tipo: "rechazado",
            mensaje: causa.message,
            detalle:
              typeof causa.details.balance_cents === "number"
                ? `Saldo disponible: ${formatCents(causa.details.balance_cents)}`
                : undefined,
          });
          onCompletada();
          return;
        }
        if (causa.esTemporal) {
          setEstado({
            tipo: "incierto",
            mensaje: `${causa.message} Puedes volver a pulsar Enviar sin riesgo de duplicar.`,
          });
          return;
        }
        claveRef.current = null;
        setEstado({ tipo: "rechazado", mensaje: causa.message });
        return;
      }
      claveRef.current = null;
      setEstado({ tipo: "rechazado", mensaje: "Ha ocurrido un error inesperado." });
    }
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-transferir">
      <h2 id="titulo-transferir">Transferir</h2>

      <form onSubmit={enviar} noValidate>
        <div className="campo">
          <label htmlFor="destino">Alias de destino</label>
          <input
            id="destino"
            value={destino}
            onChange={(e) => {
              setDestino(e.target.value.toLowerCase());
              if (estado.tipo !== "enviando") setEstado({ tipo: "inactivo" });
            }}
            placeholder="luis"
            autoComplete="off"
            required
            aria-invalid={aSiMismo}
            aria-describedby={aSiMismo ? "destino-error" : undefined}
          />
          {aSiMismo ? (
            <p id="destino-error" className="campo__error">
              No puedes transferirte a tu propia cuenta.
            </p>
          ) : null}
        </div>

        <div className="campo">
          <label htmlFor="importe">Importe en soles simulados</label>
          <div className="campo__prefijado">
            <span aria-hidden="true">S/</span>
            <input
              id="importe"
              inputMode="decimal"
              value={importe}
              onChange={(e) => {
                setImporte(e.target.value);
                if (estado.tipo !== "enviando") setEstado({ tipo: "inactivo" });
              }}
              placeholder="30.00"
              autoComplete="off"
              required
              aria-invalid={errorImporte !== null || sinSaldo}
              aria-describedby="importe-ayuda"
            />
          </div>
          <p id="importe-ayuda" className={errorImporte || sinSaldo ? "campo__error" : "campo__ayuda"}>
            {errorImporte ??
              (sinSaldo
                ? "El importe supera tu saldo disponible."
                : importeCents !== null
                  ? `Se enviarán ${formatCents(importeCents)}`
                  : "Como mucho dos decimales.")}
          </p>
        </div>

        <div className="campo">
          <label htmlFor="concepto">
            Concepto <span className="campo__opcional">(opcional)</span>
          </label>
          <input
            id="concepto"
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
            maxLength={140}
            autoComplete="off"
          />
        </div>

        {estado.tipo === "hecho" ? (
          <Aviso
            tono="exito"
            titulo="Transferencia completada"
            onCerrar={() => setEstado({ tipo: "inactivo" })}
          >
            Enviaste {formatCents(estado.transferencia.amount_cents)} a{" "}
            <strong>{estado.transferencia.destination_alias}</strong>.
            <br />
            <span className="monoespacio">
              Operación {estado.transferencia.id}
            </span>
          </Aviso>
        ) : null}

        {estado.tipo === "rechazado" ? (
          <Aviso
            tono="error"
            titulo="No se realizó la transferencia"
            onCerrar={() => setEstado({ tipo: "inactivo" })}
          >
            {estado.mensaje}
            {estado.detalle ? (
              <>
                <br />
                {estado.detalle}
              </>
            ) : null}
          </Aviso>
        ) : null}

        {estado.tipo === "incierto" ? (
          <Aviso tono="informacion" titulo="Resultado no confirmado">
            {estado.mensaje}
          </Aviso>
        ) : null}

        <button
          type="submit"
          className="boton boton--principal"
          disabled={!puedeEnviar}
        >
          {estado.tipo === "enviando" ? (
            <Cargando texto="Enviando" />
          ) : estado.tipo === "incierto" ? (
            "Reintentar envío"
          ) : (
            "Enviar"
          )}
        </button>
      </form>
    </section>
  );
}
