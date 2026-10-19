"""Punto único de importación de todos los modelos.

Alembic y las pruebas importan este módulo para que `Base.metadata` contenga
el esquema completo. Sin esto, autogenerate vería tablas a medias.
"""

from app.modules.accounts.models import Account
from app.modules.identity.models import User
from app.modules.idempotency.models import IdempotencyKey
from app.modules.ledger.models import LedgerEntry
from app.modules.transfers.models import Transfer
from app.platform.db import Base

__all__ = ["Account", "Base", "IdempotencyKey", "LedgerEntry", "Transfer", "User"]
