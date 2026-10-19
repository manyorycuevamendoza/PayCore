import { Acceso } from "./components/Acceso";
import { Aviso } from "./components/Aviso";
import { Panel } from "./components/Panel";
import { useAuth } from "./hooks/useAuth";

export default function App() {
  const { token, setToken, cerrarSesion } = useAuth();

  return (
    <div className="app">
      <div className="franja-prototipo" role="note">
        <strong>Prototipo educativo.</strong> Los fondos son{" "}
        <strong>simulados</strong> y no tienen ningún valor. PayCore no está
        conectado a ninguna entidad bancaria ni pasarela de pago.
      </div>

      {token === null ? (
        <Acceso onSesion={setToken} />
      ) : (
        <Panel
          token={token}
          onSesionCaducada={cerrarSesion}
          onCerrarSesion={cerrarSesion}
        />
      )}

      <footer className="pie">
        <Aviso tono="informacion">
          Proyecto de portafolio de Manyory Estefany Cueva Mendoza. Sin relación
          ni afiliación con ninguna marca comercial.
        </Aviso>
      </footer>
    </div>
  );
}
