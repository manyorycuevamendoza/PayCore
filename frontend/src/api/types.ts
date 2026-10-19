/** Tipos del contrato de la API. Espejo de docs/openapi.json. */

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
    details: Record<string, unknown>;
  };
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  alias: string;
}

export interface AccountResponse {
  id: string;
  alias: string;
  currency: string;
  /** Entero de céntimos. Nunca se opera con decimales en el cliente. */
  balance_cents: number;
  balance_display: string;
  owner_full_name: string;
}

export interface BalanceResponse {
  account_id: string;
  currency: string;
  balance_cents: number;
  balance_display: string;
  as_of: string;
}

export interface TransferResponse {
  id: string;
  status: "completed" | "rejected" | "pending";
  amount_cents: number;
  amount_display: string;
  currency: string;
  source_alias: string;
  destination_alias: string;
  concept: string | null;
  created_at: string;
  completed_at: string | null;
  source_balance_after_cents: number | null;
  rejection_reason: string | null;
}

export interface Movement {
  transfer_id: string;
  direction: "in" | "out";
  amount_cents: number;
  amount_display: string;
  signed_amount_cents: number;
  balance_after_cents: number;
  counterparty_alias: string;
  concept: string | null;
  created_at: string;
}

export interface MovementPage {
  items: Movement[];
  limit: number;
  offset: number;
  total: number;
}
