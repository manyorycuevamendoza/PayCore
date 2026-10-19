import { formatCents, formatDateTime } from "../api/money";
import type { Movement } from "../api/types";
import { Esqueleto } from "./Cargando";

export function Historial({
  movimientos,
  total,
  cargando,
  puedeVerMas,
  onVerMas,
}: {
  movimientos: Movement[];
  total: number;
  cargando: boolean;
  puedeVerMas: boolean;
  onVerMas: () => void;
}) {
  return (
    <section className="tarjeta" aria-labelledby="titulo-historial">
      <div className="tarjeta__cabecera">
        <h2 id="titulo-historial">Movimientos</h2>
        {!cargando ? (
          <span className="etiqueta">{total}</span>
        ) : null}
      </div>

      {cargando && movimientos.length === 0 ? (
        <ul className="movimientos">
          {[0, 1, 2].map((i) => (
            <li key={i} className="movimiento">
              <Esqueleto ancho="60%" />
              <Esqueleto ancho="25%" />
            </li>
          ))}
        </ul>
      ) : movimientos.length === 0 ? (
        <p className="vacio">
          Todavía no hay movimientos. Cuando envíes o recibas dinero simulado
          aparecerá aquí.
        </p>
      ) : (
        <ul className="movimientos">
          {movimientos.map((m) => (
            <li
              key={`${m.transfer_id}-${m.direction}`}
              className={`movimiento movimiento--${m.direction}`}
            >
              <span className="movimiento__icono" aria-hidden="true">
                {m.direction === "in" ? "↓" : "↑"}
              </span>
              <div className="movimiento__detalle">
                <span className="movimiento__contraparte">
                  {m.direction === "in" ? "De" : "A"} {m.counterparty_alias}
                </span>
                <span className="movimiento__fecha">
                  {formatDateTime(m.created_at)}
                  {m.concept ? ` · ${m.concept}` : ""}
                </span>
              </div>
              <div className="movimiento__cifras">
                <span className="movimiento__importe">
                  {m.direction === "in" ? "+" : "−"}
                  {formatCents(m.amount_cents)}
                </span>
                <span className="movimiento__saldo">
                  Saldo {formatCents(m.balance_after_cents)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {puedeVerMas ? (
        <button
          type="button"
          className="boton boton--secundario"
          onClick={onVerMas}
          disabled={cargando}
        >
          {cargando ? "Cargando" : "Ver más"}
        </button>
      ) : null}
    </section>
  );
}
