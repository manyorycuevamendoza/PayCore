"""Representación del dinero. Ver ADR-0003.

Dentro del dominio y de la base de datos, los importes son SIEMPRE enteros de
céntimos. La conversión a decimal ocurre solo en la frontera de la API, para
que ninguna operación aritmética toque punto flotante.
"""

from __future__ import annotations

from decimal import Decimal

CURRENCY = "PEN"
CENTS_PER_UNIT = 100

# Tope por operación. No es una regla contable, es un control de abuso:
# limita el daño de un error de cliente y acota el espacio de pruebas.
MAX_TRANSFER_CENTS = 1_000_000_00  # S/ 1 000 000,00 simulados


def cents_to_display(cents: int) -> str:
    """Convierte céntimos a una cadena decimal con dos cifras, sin float."""
    signo = "-" if cents < 0 else ""
    unidades, resto = divmod(abs(cents), CENTS_PER_UNIT)
    return f"{signo}{unidades}.{resto:02d}"


def cents_to_decimal(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(CENTS_PER_UNIT)
