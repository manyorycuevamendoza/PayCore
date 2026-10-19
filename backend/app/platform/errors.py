"""Errores de dominio de PayCore.

Cada error lleva un código estable que la API expone al cliente y que las
pruebas usan como aserción. El mensaje es para una persona; el código, para
una máquina.
"""

from __future__ import annotations

from typing import Any


class PayCoreError(Exception):
    """Raíz de todos los errores de dominio."""

    code: str = "internal_error"
    http_status: int = 500
    message: str = "Ha ocurrido un error inesperado."

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(self.message)


class ValidationError(PayCoreError):
    code = "validation_error"
    http_status = 422
    message = "La petición no es válida."


class AuthenticationError(PayCoreError):
    code = "authentication_failed"
    http_status = 401
    message = "Credenciales inválidas."


class NotFoundError(PayCoreError):
    code = "not_found"
    http_status = 404
    message = "El recurso solicitado no existe."


class EmailAlreadyRegisteredError(PayCoreError):
    code = "email_already_registered"
    http_status = 409
    message = "Ese correo ya está registrado."


class InsufficientFundsError(PayCoreError):
    code = "insufficient_funds"
    http_status = 422
    message = "El saldo disponible no cubre el importe solicitado."


class SameAccountTransferError(PayCoreError):
    code = "same_account_transfer"
    http_status = 422
    message = "La cuenta de origen y la de destino no pueden ser la misma."


class IdempotencyKeyRequiredError(PayCoreError):
    code = "idempotency_key_required"
    http_status = 400
    message = "Esta operación exige la cabecera Idempotency-Key."


class IdempotencyKeyInProgressError(PayCoreError):
    code = "idempotency_key_in_progress"
    http_status = 409
    message = "Ya hay una petición en curso con esa clave de idempotencia."


class IdempotencyKeyReusedError(PayCoreError):
    code = "idempotency_key_reused"
    http_status = 422
    message = "Esa clave de idempotencia ya se usó con un cuerpo distinto."


class RateLimitExceededError(PayCoreError):
    code = "rate_limit_exceeded"
    http_status = 429
    message = "Demasiadas peticiones. Inténtalo de nuevo en unos segundos."


class ConcurrencyRetryExhaustedError(PayCoreError):
    code = "concurrency_retry_exhausted"
    http_status = 503
    message = "El sistema está muy cargado. Vuelve a intentarlo."
