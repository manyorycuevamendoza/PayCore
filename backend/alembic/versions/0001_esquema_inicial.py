"""Esquema inicial de PayCore: usuarios, cuentas, transferencias, ledger e idempotencia.

Esta migración crea también las garantías que viven en el motor y no en la
aplicación (ver docs/architecture.md, sección 3.1):

- I1  saldo de usuario no negativo (CHECK)
- I2  importe de transferencia estrictamente positivo (CHECK)
- I3  origen distinto de destino (CHECK)
- I4  cada transferencia tiene exactamente dos asientos que suman cero
      (trigger de restricción diferido al COMMIT)
- I10 el ledger es de solo inserción (trigger que rechaza UPDATE y DELETE)

Revision ID: 0001_esquema_inicial
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_esquema_inicial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEDGER_BALANCED_FN = """
CREATE OR REPLACE FUNCTION paycore_check_ledger_balanced() RETURNS trigger AS $$
DECLARE
    v_count integer;
    v_sum   bigint;
BEGIN
    SELECT count(*), coalesce(sum(amount_cents), 0)
      INTO v_count, v_sum
      FROM ledger_entries
     WHERE transfer_id = NEW.transfer_id;

    IF v_count <> 2 THEN
        RAISE EXCEPTION
            'ledger desbalanceado: la transferencia % tiene % asientos y se esperaban 2',
            NEW.transfer_id, v_count
            USING ERRCODE = 'check_violation';
    END IF;

    IF v_sum <> 0 THEN
        RAISE EXCEPTION
            'ledger desbalanceado: los asientos de la transferencia % suman % y se esperaba 0',
            NEW.transfer_id, v_sum
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

LEDGER_APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION paycore_ledger_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'ledger_entries es de solo inserción: la operación % no está permitida', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # CITEXT da unicidad de correo insensible a mayúsculas en el propio motor.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(full_name) BETWEEN 1 AND 120", name="ck_users_full_name_len"
        ),
        sa.CheckConstraint(
            "char_length(email::text) BETWEEN 3 AND 254", name="ck_users_email_len"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alias", sa.String(length=32), nullable=False),
        sa.Column(
            "kind", sa.String(length=16), server_default=sa.text("'user'"), nullable=False
        ),
        sa.Column(
            "currency", sa.String(length=3), server_default=sa.text("'PEN'"), nullable=False
        ),
        sa.Column(
            "balance_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind = 'system' OR balance_cents >= 0", name="ck_accounts_balance_no_negativo"
        ),
        sa.CheckConstraint("kind IN ('user', 'system')", name="ck_accounts_kind"),
        sa.CheckConstraint("currency = 'PEN'", name="ck_accounts_currency_pen"),
        sa.CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL) "
            "OR (kind = 'system' AND user_id IS NULL)",
            name="ck_accounts_propiedad_coherente",
        ),
        sa.CheckConstraint(
            "char_length(alias) BETWEEN 3 AND 32", name="ck_accounts_alias_len"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias"),
        sa.UniqueConstraint("user_id", name="uq_accounts_user_id"),
    )

    op.create_table(
        "transfers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rejection_reason", sa.String(length=64), nullable=True),
        sa.Column("concept", sa.String(length=140), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_cents > 0", name="ck_transfers_importe_positivo"),
        sa.CheckConstraint(
            "source_account_id <> destination_account_id",
            name="ck_transfers_origen_distinto_destino",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'rejected')", name="ck_transfers_status"
        ),
        sa.CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_transfers_motivo_coherente",
        ),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_transfers_completado_coherente",
        ),
        sa.ForeignKeyConstraint(
            ["source_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destination_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transfers_source_created", "transfers", ["source_account_id", "created_at"]
    )
    op.create_index(
        "ix_transfers_destination_created",
        "transfers",
        ["destination_account_id", "created_at"],
    )

    op.create_table(
        "ledger_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_cents <> 0", name="ck_ledger_importe_no_nulo"),
        sa.ForeignKeyConstraint(["transfer_id"], ["transfers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_id", "account_id", name="uq_ledger_transfer_account"),
    )
    op.create_index("ix_ledger_account_created", "ledger_entries", ["account_id", "created_at"])
    op.create_index("ix_ledger_transfer", "ledger_entries", ["transfer_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('in_progress', 'succeeded', 'failed')", name="ck_idempotency_state"
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 8 AND 255", name="ck_idempotency_key_len"
        ),
        sa.CheckConstraint(
            "(state = 'in_progress') OR (response_status IS NOT NULL)",
            name="ck_idempotency_respuesta_coherente",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transfer_id"], ["transfers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )
    op.create_index("ix_idempotency_expires_at", "idempotency_keys", ["expires_at"])

    # I4: verificación diferida al COMMIT. Dentro de la transacción los asientos
    # pueden estar momentáneamente descuadrados; al confirmar, no.
    op.execute(LEDGER_BALANCED_FN)
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ledger_balanced
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION paycore_check_ledger_balanced()
        """
    )

    # I10: el ledger es de solo inserción. TRUNCATE sigue siendo posible, que es
    # lo que usan las pruebas para limpiar entre casos.
    op.execute(LEDGER_APPEND_ONLY_FN)
    op.execute(
        """
        CREATE TRIGGER trg_ledger_append_only
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION paycore_ledger_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_append_only ON ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_balanced ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS paycore_ledger_append_only()")
    op.execute("DROP FUNCTION IF EXISTS paycore_check_ledger_balanced()")

    op.drop_index("ix_idempotency_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_ledger_transfer", table_name="ledger_entries")
    op.drop_index("ix_ledger_account_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_transfers_destination_created", table_name="transfers")
    op.drop_index("ix_transfers_source_created", table_name="transfers")
    op.drop_table("transfers")
    op.drop_table("accounts")
    op.drop_table("users")
