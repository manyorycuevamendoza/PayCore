export function Cargando({ texto = "Cargando" }: { texto?: string }) {
  return (
    <span className="cargando" role="status">
      <span className="cargando__rueda" aria-hidden="true" />
      <span className="cargando__texto">{texto}</span>
    </span>
  );
}

export function Esqueleto({ ancho = "100%" }: { ancho?: string }) {
  return <span className="esqueleto" style={{ width: ancho }} aria-hidden="true" />;
}
