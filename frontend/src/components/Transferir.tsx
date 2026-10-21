import { useEffect, useRef, useState } from "react";
import { ApiError, NetworkError, api, nuevaClaveIdempotencia } from "../api/client";
import { formatCents } from "../api/money";
import { validarEnvio } from "../api/transfer-validation";
import type { TransferResponse } from "../api/types";
import { Aviso } from "./Aviso";
import { Cargando } from "./Cargando";

type Estado =
  | { tipo: "inactivo" | "revision" | "enviando" }
  | { tipo: "hecho"; transferencia: TransferResponse }
  | { tipo: "rechazado" | "incierto"; mensaje: string };

type Operacion = {
  clave: string;
  datos: { destination_alias: string; amount_cents: number; concept: string | null };
};

export function Transferir({ token, saldoCents, aliasPropio, onCompletada }: {
  token: string;
  saldoCents: number | null;
  aliasPropio: string;
  onCompletada: () => void;
}) {
  const [destino, setDestino] = useState("");
  const [importe, setImporte] = useState("");
  const [concepto, setConcepto] = useState("");
  const [estado, setEstado] = useState<Estado>({ tipo: "inactivo" });
  // El cuerpo y la clave se conservan juntos hasta conocer el resultado.
  const operacion = useRef<Operacion | null>(null);
  const enCurso = useRef(false);
  const resumen = useRef<HTMLHeadingElement>(null);
  const destinoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (estado.tipo === "revision" || estado.tipo === "hecho") resumen.current?.focus();
  }, [estado.tipo]);

  const { alias, centimos, errorImporte, errorDestino, sinSaldo, motivo } =
    validarEnvio(destino, importe, aliasPropio, saldoCents);
  const revisando = ["revision", "enviando", "incierto"].includes(estado.tipo);

  function revisar(evento: React.FormEvent) {
    evento.preventDefault();
    if (motivo || centimos === null || enCurso.current) return;
    operacion.current = {
      clave: nuevaClaveIdempotencia(),
      datos: { destination_alias: alias, amount_cents: centimos, concept: concepto.trim() || null },
    };
    setEstado({ tipo: "revision" });
  }

  async function enviar() {
    const intento = operacion.current;
    if (!intento || enCurso.current) return;
    enCurso.current = true;
    setEstado({ tipo: "enviando" });
    try {
      const transferencia = await api.transferir(token, intento.clave, intento.datos);
      if (transferencia.status === "pending") {
        setEstado({ tipo: "incierto", mensaje: "El envío sigue pendiente. Reintenta para consultar el resultado de esta misma operación." });
        return;
      }
      operacion.current = null;
      if (transferencia.status === "rejected") {
        setEstado({ tipo: "rechazado", mensaje: "El envío fue rechazado. Revisa el saldo y los datos antes de volver a intentarlo." });
      } else {
        setEstado({ tipo: "hecho", transferencia });
        setDestino(""); setImporte(""); setConcepto("");
      }
      onCompletada();
    } catch (causa) {
      if (causa instanceof NetworkError || (causa instanceof ApiError && causa.esTemporal)) {
        setEstado({ tipo: "incierto", mensaje: "Todavía no sabemos si el envío se completó. Conservamos sus datos: reintenta esta misma operación sin duplicar el envío." });
        return;
      }
      // Una respuesta inesperada tampoco demuestra que la operación falló.
      if (!(causa instanceof ApiError)) {
        setEstado({ tipo: "incierto", mensaje: "No pudimos confirmar el resultado. Reintenta esta misma operación para evitar duplicados." });
        return;
      }
      operacion.current = null;
      setEstado({ tipo: "rechazado", mensaje: causa.message });
      if (causa.code === "insufficient_funds") onCompletada();
    } finally { enCurso.current = false; }
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-transferir">
      <div className="tarjeta__cabecera">
        <h2 id="titulo-transferir">Enviar dinero simulado</h2>
        <span className="etiqueta">{revisando ? "Paso 2 de 2" : "Paso 1 de 2"}</span>
      </div>
      <p className="seccion__descripcion">{revisando ? "Comprueba los datos antes de confirmar." : "Indica a quién y cuánto. Podrás revisarlo antes de enviar."}</p>

      {estado.tipo === "hecho" ? (
        <Aviso tono="exito" titulo="Transferencia completada">
          <h3 ref={resumen} tabIndex={-1} className="comprobante__importe">{formatCents(estado.transferencia.amount_cents)}</h3>
          Enviados a <strong>@{estado.transferencia.destination_alias}</strong>.
          <p className="campo__ayuda">Puedes consultar este envío en Movimientos.</p>
          <details><summary>Ver comprobante</summary><span className="monoespacio">Operación {estado.transferencia.id}</span></details>
        </Aviso>
      ) : null}
      {estado.tipo === "rechazado" ? <Aviso tono="error" titulo="No se realizó la transferencia">{estado.mensaje} Tus datos se conservan para que puedas corregirlos.</Aviso> : null}

      {revisando && operacion.current ? (
        <div aria-busy={estado.tipo === "enviando"}>
          <h3 ref={resumen} tabIndex={-1} className="revision__titulo">Revisa tu envío</h3>
          <dl className="revision">
            <div><dt>Desde tu cuenta</dt><dd>@{aliasPropio}</dd></div>
            <div><dt>Para el alias</dt><dd>@{operacion.current.datos.destination_alias}</dd></div>
            <div><dt>Importe simulado</dt><dd>{formatCents(operacion.current.datos.amount_cents)}</dd></div>
            {operacion.current.datos.concept ? <div><dt>Concepto</dt><dd>{operacion.current.datos.concept}</dd></div> : null}
            {estado.tipo === "revision" && saldoCents !== null ? <div><dt>Te quedaría</dt><dd>{formatCents(saldoCents - operacion.current.datos.amount_cents)}</dd></div> : null}
          </dl>
          {estado.tipo === "incierto" ? <Aviso tono="informacion" titulo="Resultado sin confirmar">{estado.mensaje}</Aviso> : null}
          <button type="button" className="boton boton--principal" disabled={estado.tipo === "enviando"} onClick={() => void enviar()}>
            {estado.tipo === "enviando" ? <Cargando texto="Confirmando envío…" /> : estado.tipo === "incierto" ? "Reintentar el mismo envío" : `Confirmar envío de ${formatCents(operacion.current.datos.amount_cents)}`}
          </button>
          {estado.tipo === "revision" ? <button type="button" className="boton boton--secundario" onClick={() => {
            operacion.current = null;
            setEstado({ tipo: "inactivo" });
            requestAnimationFrame(() => destinoInput.current?.focus());
          }}>Volver y corregir</button> : null}
        </div>
      ) : (
        <form onSubmit={revisar}>
          <div className="campo">
            <label htmlFor="destino">Alias de quien recibe</label>
            <input ref={destinoInput} id="destino" value={destino} onChange={(e) => setDestino(e.target.value.toLowerCase())} placeholder="Ejemplo: luis" autoComplete="off" autoCapitalize="none" spellCheck={false} required maxLength={32} aria-invalid={!!errorDestino} aria-describedby="destino-ayuda" />
            <p id="destino-ayuda" className={errorDestino ? "campo__error" : "campo__ayuda"}>{errorDestino ?? "Pide a la otra persona el alias de su cuenta PayCore."}</p>
          </div>
          <div className="campo">
            <label htmlFor="importe">¿Cuánto quieres enviar?</label>
            <div className="campo__prefijado"><span aria-hidden="true">S/</span>
              <input id="importe" inputMode="decimal" value={importe} onChange={(e) => setImporte(e.target.value)} placeholder="0.00" autoComplete="off" required aria-invalid={!!errorImporte || sinSaldo} aria-describedby="importe-ayuda saldo-ayuda" />
            </div>
            <p id="saldo-ayuda" className="campo__ayuda">Disponible: {saldoCents === null ? "Cargando…" : `${formatCents(saldoCents)} simulados`}</p>
            <p id="importe-ayuda" className={errorImporte || sinSaldo ? "campo__error" : "campo__ayuda"}>{errorImporte ?? (sinSaldo ? "El importe supera tu saldo. Escribe una cantidad menor." : "Usa hasta dos decimales. Ejemplo: 30.50")}</p>
          </div>
          <div className="campo">
            <label htmlFor="concepto">Concepto <span className="campo__opcional">(opcional)</span></label>
            <input id="concepto" value={concepto} onChange={(e) => setConcepto(e.target.value)} maxLength={140} placeholder="Ejemplo: Almuerzo" autoComplete="off" />
          </div>
          <button type="submit" className="boton boton--principal" disabled={motivo !== null} aria-describedby="envio-ayuda">Revisar envío →</button>
          <p id="envio-ayuda" className="campo__ayuda">{motivo ?? "Revisar los datos todavía no realiza la transferencia."}</p>
        </form>
      )}
    </section>
  );
}
