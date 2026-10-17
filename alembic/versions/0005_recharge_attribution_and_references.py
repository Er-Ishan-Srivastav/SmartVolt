"""Add permanent recharge references and separate actor from tenant context.

Revision ID: 0005_recharge_refs
Revises: 0004_identity_and_room_lifecycle
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_recharge_refs"
down_revision = "0004_identity_and_room_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    # Batch mode is required because SQLite cannot ALTER TABLE to add a foreign key.
    naming_convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("recharges", naming_convention=naming_convention) as batch:
        batch.add_column(sa.Column("recharge_code", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_recharges_actor_user_id_users", "users", ["actor_user_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("wallet_ledger", naming_convention=naming_convention) as batch:
        batch.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_wallet_ledger_actor_user_id_users", "users", ["actor_user_id"], ["id"], ondelete="SET NULL"
        )

    # Existing transactions predate actor attribution. Do not invent who performed them.
    ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM recharges ORDER BY id")).all()]
    for sequence, recharge_id in enumerate(ids, start=1):
        connection.execute(
            sa.text("UPDATE recharges SET recharge_code = :code WHERE id = :id"),
            {"code": f"RCH-{sequence:06d}", "id": recharge_id},
        )

    # Reuse the shared public-code counter introduced in migration 0004.
    counter_exists = connection.execute(
        sa.text("SELECT prefix FROM identifier_counters WHERE prefix = 'RCH'")
    ).first()
    if counter_exists:
        connection.execute(
            sa.text("UPDATE identifier_counters SET last_value = :last_value WHERE prefix = 'RCH'"),
            {"last_value": len(ids)},
        )
    else:
        connection.execute(
            sa.text("INSERT INTO identifier_counters (prefix, last_value) VALUES ('RCH', :last_value)"),
            {"last_value": len(ids)},
        )

    # Empty-room recharges are valid. Nullable user_id represents optional tenant context,
    # not the transaction actor; actor_user_id is deliberately independent.
    with op.batch_alter_table("recharges") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("recharge_code", existing_type=sa.String(length=20), nullable=False)

    op.create_index("ix_recharges_recharge_code", "recharges", ["recharge_code"], unique=True)
    op.create_index("ix_recharges_actor_created", "recharges", ["actor_user_id", "created_at"])


def downgrade() -> None:
    # Historical rows can legitimately have no tenant context after this migration,
    # so downgrade refuses to reintroduce NOT NULL if such records exist.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM recharges WHERE user_id IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade: at least one recharge has no tenant context")
    op.drop_index("ix_recharges_actor_created", table_name="recharges")
    op.drop_index("ix_recharges_recharge_code", table_name="recharges")
    with op.batch_alter_table("wallet_ledger") as batch:
        batch.drop_column("actor_user_id")
    with op.batch_alter_table("recharges") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("actor_user_id")
        batch.drop_column("recharge_code")
    bind.execute(sa.text("DELETE FROM identifier_counters WHERE prefix = 'RCH'"))
