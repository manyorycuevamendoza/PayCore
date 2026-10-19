"""Configuración de PayCore leída del entorno.

Todos los valores llevan el prefijo PAYCORE_. No hay secretos por defecto:
en producción el arranque falla si falta JWT_SECRET.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ConcurrencyStrategy(StrEnum):
    """Estrategia de control de concurrencia. Ver ADR-0005."""

    PESSIMISTIC = "pessimistic"
    SERIALIZABLE = "serializable"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PAYCORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://paycore:paycore@localhost:5432/paycore"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15

    concurrency_strategy: ConcurrencyStrategy = ConcurrencyStrategy.PESSIMISTIC
    serializable_max_retries: int = 3

    idempotency_ttl_hours: int = 24

    # Limitación de peticiones. Ráfaga y ritmo sostenido por minuto.
    # El login se limita por IP y la transferencia por usuario autenticado.
    rate_limit_enabled: bool = True
    login_rate_burst: int = 5
    login_rate_per_minute: int = 10
    transfer_rate_burst: int = 10
    transfer_rate_per_minute: int = 60
    max_request_bytes: int = 16 * 1024

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # RFC 7518, sección 3.2: con HS256 la clave debe tener al menos el tamaño
    # de la salida de la función hash, 32 bytes. PyJWT avisa por debajo de eso.
    MIN_SECRET_BYTES: int = 32

    @field_validator("jwt_secret")
    @classmethod
    def _secret_valido(cls, value: str, info) -> str:
        environment = info.data.get("environment", Environment.DEVELOPMENT)
        if not value:
            if environment == Environment.PRODUCTION:
                raise ValueError(
                    "PAYCORE_JWT_SECRET es obligatorio cuando "
                    "PAYCORE_ENVIRONMENT=production"
                )
            return value
        if len(value.encode("utf-8")) < 32:
            raise ValueError(
                "PAYCORE_JWT_SECRET debe tener al menos 32 bytes (RFC 7518, 3.2). "
                'Genéralo con: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
