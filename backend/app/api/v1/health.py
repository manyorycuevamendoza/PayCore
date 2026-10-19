"""Sonda de salud. No requiere autenticación."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.platform.config import Settings, get_settings
from app.platform.db import get_db_session

router = APIRouter(tags=["salud"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    concurrency_strategy: str


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
def health(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - la sonda no debe propagar el fallo
        database = "unreachable"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        environment=settings.environment.value,
        database=database,
        concurrency_strategy=settings.concurrency_strategy.value,
    )
