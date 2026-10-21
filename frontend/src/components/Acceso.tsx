import { useState } from "react";
import { ApiError, NetworkError, api } from "../api/client";
import { Aviso } from "./Aviso";
import { Cargando } from "./Cargando";

type Modo = "entrar" | "registrarse";

export function Acceso({ onSesion }: { onSesion: (token: string) => void }) {
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nombre, setNombre] = useState("");
  const [alias, setAlias] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      if (modo === "registrarse") {
        await api.registrar({
          email,
          password,
          full_name: nombre,
          alias,
        });
      }
      const { access_token } = await api.iniciarSesion({ email, password });
      onSesion(access_token);
    } catch (causa) {
      if (causa instanceof ApiError) {
        setError(causa.message);
      } else if (causa instanceof NetworkError) {
        setError(causa.message);
      } else {
        setError("Ha ocurrido un error inesperado.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="acceso">
      <div className="tarjeta tarjeta--acceso">
        <header className="acceso__cabecera">
          <h1 className="marca">PayCore</h1>
          <p className="acceso__lema">Billetera digital con fondos simulados</p>
        </header>

        <div className="pestanas" role="group" aria-label="Acceso">
          <button
            type="button"
            disabled={enviando}
            aria-pressed={modo === "entrar"}
            className={`pestana ${modo === "entrar" ? "pestana--activa" : ""}`}
            onClick={() => {
              setModo("entrar");
              setError(null);
            }}
          >
            Iniciar sesión
          </button>
          <button
            type="button"
            disabled={enviando}
            aria-pressed={modo === "registrarse"}
            className={`pestana ${modo === "registrarse" ? "pestana--activa" : ""}`}
            onClick={() => {
              setModo("registrarse");
              setError(null);
            }}
          >
            Crear cuenta
          </button>
        </div>

        <h2>{modo === "entrar" ? "Tu billetera de prueba" : "Crea tu billetera de prueba"}</h2>
        <p className="seccion__descripcion">{modo === "entrar" ? "Ingresa para consultar tu saldo y enviar fondos simulados." : "Elige un alias para recibir transferencias. Tu cuenta empieza sin saldo."}</p>
        <form onSubmit={enviar}>
          <fieldset disabled={enviando} className="formulario__campos">
          {modo === "registrarse" ? (
            <>
              <div className="campo">
                <label htmlFor="nombre">Nombre completo</label>
                <input
                  id="nombre"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  autoComplete="name"
                  required
                  maxLength={120}
                />
              </div>
              <div className="campo">
                <label htmlFor="alias">Alias para recibir</label>
                <input
                  id="alias"
                  value={alias}
                  onChange={(e) => setAlias(e.target.value.toLowerCase())}
                  pattern="[a-z0-9][a-z0-9._\-]{2,31}"
                  required
                  aria-describedby="alias-ayuda"
                />
                <p id="alias-ayuda" className="campo__ayuda">
                  Entre 3 y 32 caracteres: minúsculas, dígitos, punto, guion o
                  guion bajo.
                </p>
              </div>
            </>
          ) : null}

          <div className="campo">
            <label htmlFor="email">Correo</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className="campo">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={
                modo === "registrarse" ? "new-password" : "current-password"
              }
              minLength={modo === "registrarse" ? 10 : 1}
              required
              aria-describedby={
                modo === "registrarse" ? "password-ayuda" : undefined
              }
            />
            {modo === "registrarse" ? (
              <p id="password-ayuda" className="campo__ayuda">
                Diez caracteres como mínimo.
              </p>
            ) : null}
          </div>

          </fieldset>
          {error ? <Aviso tono="error">{error}</Aviso> : null}

          <button type="submit" className="boton boton--principal" disabled={enviando}>
            {enviando ? (
              <Cargando texto={modo === "entrar" ? "Entrando" : "Creando cuenta"} />
            ) : modo === "entrar" ? (
              "Iniciar sesión"
            ) : (
              "Crear cuenta"
            )}
          </button>
        </form>
      </div>
    </main>
  );
}
