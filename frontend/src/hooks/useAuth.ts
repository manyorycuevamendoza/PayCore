import { useCallback, useEffect, useState } from "react";

const CLAVE = "paycore.token";

/**
 * Sesión del usuario.
 *
 * El token se guarda en sessionStorage, que se borra al cerrar la pestaña.
 * Es una concesión a la usabilidad del prototipo con un coste declarado:
 * cualquier XSS podría leerlo. La respuesta correcta en producción es una
 * cookie httpOnly con protección CSRF, que exige que el backend y el frontend
 * compartan origen. Está anotado como limitación en el README.
 */
export function useAuth() {
  const [token, setToken] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(CLAVE);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      if (token) sessionStorage.setItem(CLAVE, token);
      else sessionStorage.removeItem(CLAVE);
    } catch {
      // Navegador con almacenamiento bloqueado: la sesión vive solo en memoria.
    }
  }, [token]);

  const cerrarSesion = useCallback(() => setToken(null), []);

  return { token, setToken, cerrarSesion, autenticada: token !== null };
}
