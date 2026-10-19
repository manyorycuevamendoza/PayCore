"""H2. Las invariantes se verifican atacando la base de datos directamente.

Ninguna de estas pruebas pasa por la aplicación. Si una restricción solo
existiera en el código Python, estas pruebas fallarían. Ese es el punto:
demostrar que las garantías viven en el motor.

Mapa de invariantes en docs/architecture.md, sección 3.1.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.conftest import (
    crear_asiento,
    crear_cuenta,
    crear_transferencia,
    crear_usuario,
)

pytestmark = [pytest.mark.integration, pytest.mark.schema]


# --- I1. Ningún saldo de usuario puede quedar negativo ----------------------


def test_i1_saldo_de_usuario_no_puede_ser_negativo(engine: Engine, limpiar: None) -> None:
    with engine.begin() as conn:
        usuario = crear_usuario(conn)
        cuenta = crear_cuenta(conn, usuario, "ana", balance_cents=10_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE accounts SET balance_cents = -1 WHERE id = :id"),
                {"id": cuenta},
            )
    assert "ck_accounts_balance_no_negativo" in str(error.value)


def test_i1_la_cuenta_de_sistema_si_puede_quedar_negativa(
    engine: Engine, limpiar: None
) -> None:
    """La exención está declarada en ADR-0004: es el origen auditado del saldo
    ficticio, y permite que la suma global de asientos siga siendo cero."""
    with engine.begin() as conn:
        sistema = crear_cuenta(
            conn, None, "SYSTEM_FUNDING", balance_cents=0, kind="system"
        )
        conn.execute(
            text("UPDATE accounts SET balance_cents = -50_000 WHERE id = :id"),
            {"id": sistema},
        )
        saldo = conn.execute(
            text("SELECT balance_cents FROM accounts WHERE id = :id"), {"id": sistema}
        ).scalar_one()
    assert saldo == -50_000


# --- I2 e I3. Importe positivo y cuentas distintas --------------------------


@pytest.mark.parametrize("importe", [0, -1, -5_000])
def test_i2_importe_de_transferencia_debe_ser_positivo(
    engine: Engine, limpiar: None, importe: int
) -> None:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            crear_transferencia(conn, ana, luis, importe)
    assert "ck_transfers_importe_positivo" in str(error.value)


def test_i3_origen_y_destino_no_pueden_coincidir(engine: Engine, limpiar: None) -> None:
    with engine.begin() as conn:
        usuario = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario, "ana", 10_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            crear_transferencia(conn, ana, ana, 1_000)
    assert "ck_transfers_origen_distinto_destino" in str(error.value)


# --- I4. Cada transferencia tiene exactamente dos asientos que suman cero ----


def test_i4_un_solo_asiento_hace_fallar_el_commit(engine: Engine, limpiar: None) -> None:
    """El trigger es DEFERRABLE INITIALLY DEFERRED: dentro de la transacción el
    asiento suelto se acepta, y es el COMMIT el que lo rechaza."""
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)

    with pytest.raises(DBAPIError) as error:
        with engine.begin() as conn:
            transferencia = crear_transferencia(conn, ana, luis, 3_000)
            crear_asiento(conn, transferencia, ana, -3_000, 7_000)
            # falta el crédito en la cuenta de Luis
    assert "ledger desbalanceado" in str(error.value)


def test_i4_dos_asientos_que_no_suman_cero_hacen_fallar_el_commit(
    engine: Engine, limpiar: None
) -> None:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)

    with pytest.raises(DBAPIError) as error:
        with engine.begin() as conn:
            transferencia = crear_transferencia(conn, ana, luis, 3_000)
            crear_asiento(conn, transferencia, ana, -3_000, 7_000)
            crear_asiento(conn, transferencia, luis, 9_999, 11_999)  # dinero creado
    assert "suman" in str(error.value)


def test_i4_el_par_correcto_si_se_confirma(engine: Engine, limpiar: None) -> None:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)
        transferencia = crear_transferencia(conn, ana, luis, 3_000)
        crear_asiento(conn, transferencia, ana, -3_000, 7_000)
        crear_asiento(conn, transferencia, luis, 3_000, 5_000)

    with engine.connect() as conn:
        suma = conn.execute(
            text("SELECT coalesce(sum(amount_cents), 0) FROM ledger_entries")
        ).scalar_one()
    assert suma == 0


def test_i4_una_transferencia_no_puede_tocar_dos_veces_la_misma_cuenta(
    engine: Engine, limpiar: None
) -> None:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            transferencia = crear_transferencia(conn, ana, luis, 3_000)
            crear_asiento(conn, transferencia, ana, -3_000, 7_000)
            crear_asiento(conn, transferencia, ana, 3_000, 10_000)
    assert "uq_ledger_transfer_account" in str(error.value)


# --- I10. El ledger es de solo inserción ------------------------------------


def _ledger_con_un_par(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)
        transferencia = crear_transferencia(conn, ana, luis, 3_000)
        asiento = crear_asiento(conn, transferencia, ana, -3_000, 7_000)
        crear_asiento(conn, transferencia, luis, 3_000, 5_000)
    return transferencia, asiento


def test_i10_no_se_puede_actualizar_un_asiento(engine: Engine, limpiar: None) -> None:
    _, asiento = _ledger_con_un_par(engine)
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE ledger_entries SET amount_cents = 1 WHERE id = :id"),
                {"id": asiento},
            )
    assert "solo inserción" in str(error.value)


def test_i10_no_se_puede_borrar_un_asiento(engine: Engine, limpiar: None) -> None:
    _, asiento = _ledger_con_un_par(engine)
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM ledger_entries WHERE id = :id"), {"id": asiento}
            )
    assert "solo inserción" in str(error.value)


# --- Coherencia de estados y propiedad --------------------------------------


def test_una_transferencia_rechazada_debe_llevar_motivo(
    engine: Engine, limpiar: None
) -> None:
    with engine.begin() as conn:
        usuario_a = crear_usuario(conn)
        usuario_b = crear_usuario(conn)
        ana = crear_cuenta(conn, usuario_a, "ana", 10_000)
        luis = crear_cuenta(conn, usuario_b, "luis", 2_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO transfers (source_account_id, destination_account_id, "
                    "amount_cents, status) VALUES (:o, :d, 1000, 'rejected')"
                ),
                {"o": ana, "d": luis},
            )
    assert "ck_transfers_motivo_coherente" in str(error.value)


def test_una_cuenta_de_usuario_no_puede_quedar_sin_dueno(
    engine: Engine, limpiar: None
) -> None:
    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            crear_cuenta(conn, None, "huerfana", 0, kind="user")
    assert "ck_accounts_propiedad_coherente" in str(error.value)


def test_un_usuario_solo_puede_tener_una_cuenta_en_el_mvp(
    engine: Engine, limpiar: None
) -> None:
    with engine.begin() as conn:
        usuario = crear_usuario(conn)
        crear_cuenta(conn, usuario, "ana", 10_000)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            crear_cuenta(conn, usuario, "ana-segunda", 0)
    assert "uq_accounts_user_id" in str(error.value)


def test_el_correo_es_unico_sin_distinguir_mayusculas(
    engine: Engine, limpiar: None
) -> None:
    """CITEXT: la unicidad no depende de que la aplicación normalice."""
    with engine.begin() as conn:
        crear_usuario(conn, email="Ana.Perez@Ejemplo.Pe")

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            crear_usuario(conn, email="ana.perez@ejemplo.pe")


def test_solo_se_admite_la_moneda_pen_simulada(engine: Engine, limpiar: None) -> None:
    with engine.begin() as conn:
        usuario = crear_usuario(conn)

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts (user_id, alias, kind, currency, balance_cents) "
                    "VALUES (:u, 'ana', 'user', 'USD', 0)"
                ),
                {"u": usuario},
            )
    assert "ck_accounts_currency_pen" in str(error.value)
