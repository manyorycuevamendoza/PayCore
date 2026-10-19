/** Cliente HTTP de la API de PayCore. */

import type {
  AccountResponse,
  ApiErrorBody,
  BalanceResponse,
  MovementPage,
  TokenResponse,
  TransferResponse,
  UserResponse,
} from "./types";

const BASE_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

/** Error con el código estable que devuelve la API, no solo el texto. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
    readonly requestId: string = "",
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True cuando el servidor dice cuándo volver a intentarlo. */
  get esTemporal(): boolean {
    return this.status === 429 || this.status >= 500;
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

interface PeticionOpciones {
  method?: string;
  body?: unknown;
  token?: string | null;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

async function peticion<T>(ruta: string, opciones: PeticionOpciones = {}): Promise<T> {
  const { method = "GET", body, token, idempotencyKey, signal } = opciones;

  const cabeceras: Record<string, string> = {};
  if (body !== undefined) cabeceras["Content-Type"] = "application/json";
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  if (idempotencyKey) cabeceras["Idempotency-Key"] = idempotencyKey;

  let respuesta: Response;
  try {
    respuesta = await fetch(`${BASE_URL}${ruta}`, {
      method,
      headers: cabeceras,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    });
  } catch (causa) {
    if (causa instanceof DOMException && causa.name === "AbortError") throw causa;
    // No sabemos si la petición llegó al servidor. Es exactamente el caso que
    // cubre la clave de idempotencia: reintentar con la misma clave es seguro.
    throw new NetworkError(
      "No se pudo contactar con el servidor. Comprueba tu conexión.",
    );
  }

  if (respuesta.status === 204) return undefined as T;

  const texto = await respuesta.text();
  let datos: unknown = null;
  if (texto) {
    try {
      datos = JSON.parse(texto);
    } catch {
      datos = null;
    }
  }

  if (!respuesta.ok) {
    const cuerpo = datos as ApiErrorBody | null;
    throw new ApiError(
      respuesta.status,
      cuerpo?.error?.code ?? "error_desconocido",
      cuerpo?.error?.message ?? `Error ${respuesta.status}.`,
      cuerpo?.error?.details ?? {},
      cuerpo?.error?.request_id ?? "",
    );
  }

  return datos as T;
}

/** Clave de idempotencia generada por el cliente, un UUID v4. */
export function nuevaClaveIdempotencia(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

export const api = {
  registrar: (datos: {
    email: string;
    password: string;
    full_name: string;
    alias: string;
  }) => peticion<UserResponse>("/auth/register", { method: "POST", body: datos }),

  iniciarSesion: (datos: { email: string; password: string }) =>
    peticion<TokenResponse>("/auth/login", { method: "POST", body: datos }),

  cuenta: (token: string) => peticion<AccountResponse>("/accounts/me", { token }),

  saldo: (token: string) =>
    peticion<BalanceResponse>("/accounts/me/balance", { token }),

  movimientos: (token: string, limit = 20, offset = 0) =>
    peticion<MovementPage>(
      `/accounts/me/transactions?limit=${limit}&offset=${offset}`,
      { token },
    ),

  /**
   * La clave de idempotencia la genera quien llama y se mantiene entre
   * reintentos. Esa es toda la gracia: si la respuesta se pierde, reenviar
   * con la misma clave no mueve el dinero dos veces.
   */
  transferir: (
    token: string,
    clave: string,
    datos: {
      destination_alias: string;
      amount_cents: number;
      concept?: string | null;
    },
  ) =>
    peticion<TransferResponse>("/transfers", {
      method: "POST",
      body: datos,
      token,
      idempotencyKey: clave,
    }),
};
