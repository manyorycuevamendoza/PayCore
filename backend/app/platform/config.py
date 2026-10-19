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

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("jwt_secret")
    @classmethod
    def _secret_required_outside_dev(cls, value: str, info) -> str:
        environment = info.data.get("environment", Environment.DEVELOPMENT)
        if environment == Environment.PRODUCTION and not value:
            raise ValueError(
                "PAYCORE_JWT_SECRET es obligatorio cuando PAYCORE_ENVIRONMENT=production"
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
