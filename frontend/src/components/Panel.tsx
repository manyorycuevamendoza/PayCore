import { useCallback, useEffect, useState } from "react";
import { ApiError, NetworkError, api } from "../api/client";
import { formatCents } from "../api/money";
import type { AccountResponse, Movement } from "../api/types";
import { Aviso } from "./Aviso";
import { Esqueleto } from "./Cargando";
import { Historial } from "./Historial";
import { Transferir } from "./Transferir";

const POR_PAGINA = 10;

export function Panel({
  token,
  onSesionCaducada,
  onCerrarSesion,
}: {
  token: string;
  onSesionCaducada: () => void;
  onCerrarSesion: () => void;
}) {
  const [cuenta, setCuenta] = useState<AccountResponse | null>(null);
  const [movimientos, setMovimientos] = useState<Movement[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const manejarFallo = useCallback(
    (causa: unknown) => {
      if (causa instanceof ApiError && causa.status === 401) {
        onSesionCaducada();
        return;
      }
      if (causa instanceof NetworkError) {
        setError(causa.message);
        return;
      }
      if (causa instanceof ApiError) {
        setError(causa.message);
        return;
      }
      setError("Ha ocurrido un error inesperado.");
    },
    [onSesionCaducada],
  );

  const cargar = useCallback(
    async (offset = 0) => {
      setCargando(true);
      setError(null);
      try {
        const [datosCuenta, pagina] = await Promise.all([
          api.cuenta(token),
          api.movimientos(token, POR_PAGINA, offset),
        ]);
        setCuenta(datosCuenta);
        setTotal(pagina.total);
        setMovimientos((previos) =>
          offset === 0 ? pagina.items : [...previos, ...pagina.items],
        );
      } catch (causa) {
        manejarFallo(causa);
      } finally {
        setCargando(false);
      }
    },
    [token, manejarFallo],
  );

  useEffect(() => {
    void cargar(0);
  }, [cargar]);

  return (
    <div className="panel">
      <header className="barra">
        <span className="marca marca--pequena">PayCore</span>
        <div className="barra__derecha">
          {cuenta ? (
            <span className="barra__usuario">
              {cuenta.owner_full_name}{" "}
              <span className="monoespacio">@{cuenta.alias}</span>
            </span>
          ) : null}
          <button
            type="button"
            className="boton boton--texto"
            onClick={onCerrarSesion}
          >
            Salir
          </button>
        </div>
      </header>

      <main className="panel__contenido">
        {error ? (
          <Aviso tono="error" onCerrar={() => setError(null)}>
            {error}{" "}
            <button
              type="button"
              className="boton boton--texto"
              onClick={() => void cargar(0)}
            >
              Reintentar
            </button>
          </Aviso>
        ) : null}

        <section className="tarjeta tarjeta--saldo" aria-labelledby="titulo-saldo">
          <h2 id="titulo-saldo" className="tarjeta--saldo__etiqueta">
            Saldo disponible
          </h2>
          {cuenta ? (
            <p className="saldo" aria-live="polite">
              {formatCents(cuenta.balance_cents)}
            </p>
          ) : (
            <p className="saldo">
              <Esqueleto ancho="12ch" />
            </p>
          )}
          <p className="tarjeta--saldo__nota">
            Soles peruanos simulados (PEN). Sin valor real.
          </p>
        </section>

        <div className="columnas">
          {cuenta ? (
            <Transferir
              token={token}
              saldoCents={cuenta.balance_cents}
              aliasPropio={cuenta.alias}
              onCompletada={() => void cargar(0)}
            />
          ) : null}

          <Historial
            movimientos={movimientos}
            total={total}
            cargando={cargando}
            puedeVerMas={movimientos.length < total}
            onVerMas={() => void cargar(movimientos.length)}
          />
        </div>
      </main>
    </div>
  );
}
