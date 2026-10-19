type Tono = "error" | "exito" | "informacion";

const ICONOS: Record<Tono, string> = {
  error: "⚠",
  exito: "✓",
  informacion: "ℹ",
};

export function Aviso({
  tono,
  titulo,
  children,
  onCerrar,
}: {
  tono: Tono;
  titulo?: string;
  children: React.ReactNode;
  onCerrar?: () => void;
}) {
  return (
    <div
      className={`aviso aviso--${tono}`}
      role={tono === "error" ? "alert" : "status"}
      aria-live={tono === "error" ? "assertive" : "polite"}
    >
      <span className="aviso__icono" aria-hidden="true">
        {ICONOS[tono]}
      </span>
      <div className="aviso__cuerpo">
        {titulo ? <strong className="aviso__titulo">{titulo}</strong> : null}
        <div>{children}</div>
      </div>
      {onCerrar ? (
        <button
          type="button"
          className="aviso__cerrar"
          onClick={onCerrar}
          aria-label="Cerrar aviso"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
