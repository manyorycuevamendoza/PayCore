"""Enrutador de la versión 1 de la API."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import accounts, auth, health, transfers

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(transfers.router)
