"""Logging estructurado en JSON con identificador de correlación.

Lista de denegación explícita: nunca se registran contraseñas, tokens,
cabeceras Authorization ni claves de idempotencia completas.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}

REDACTED_KEYS = {
    "password", "password_hash", "token", "access_token", "authorization",
    "jwt_secret", "secret", "idempotency_key",
}


def redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Sustituye por un marcador cualquier clave sensible."""
    return {
        key: ("[REDACTADO]" if key.lower() in REDACTED_KEYS else value)
        for key, value in payload.items()
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        payload.update(redact(extras))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True
