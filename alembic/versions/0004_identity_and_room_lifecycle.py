"""Add public identifiers and safe room/meter/tenant lifecycle fields.

Revision ID: 0004_identity_and_room_lifecycle
Revises: 0003_revocable_auth_sessions
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_identity_and_room_lifecycle"
down_revision = "0003_revocable_auth_sessions"
branch_labels = None
depends_on = None


def _backfill_codes(connection, table_name: str, column_name: str, prefix: str, where=None) -> int:
    table = sa.table(table_name, sa.column("id", sa.Integer()), sa.column(column_name, sa.String()))
    query = sa.select(table.c.id).order_by(table.c.id)
    if where is not None:
        query = query.where(where)
    ids = [row[0] for row in connection.execute(query).all()]
    for sequence, row_id in enumerate(ids, start=1):
        connection.execute(
            table.update().where(table.c.id == row_id).values({column_name: f"{prefix}-{sequence:06d}"})
        )
    return len(ids)


def upgrade() -> None:
    op.create_table(
        "identifier_counters",
        sa.Column("prefix", sa.String(length=3), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column("rooms", sa.Column("room_code", sa.String(length=20), nullable=True))
    op.add_column("rooms", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("users", sa.Column("tenant_code", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("meters", sa.Column("meter_code", sa.String(length=20), nullable=True))
    op.add_column("meters", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))

    connection = op.get_bind()
    room_count = _backfill_codes(connection, "rooms", "room_code", "ROM")
    meter_count = _backfill_codes(connection, "meters", "meter_code", "MTR")
    resident_filter = sa.text("role = 'RESIDENT'")
    tenant_count = _backfill_codes(connection, "users", "tenant_code", "TEN", resident_filter)

    # Older application versions represented removed residents by clearing login
    # fields. Preserve their identity/history but mark those accounts inactive.
    connection.execute(sa.text(
        "UPDATE users SET is_active = false "
        "WHERE role = 'RESIDENT' AND (username IS NULL OR password_hash IS NULL)"
    ))

    # Counters are initialized to the number of allocated IDs. Production inserts
    # then increment an existing counter atomically inside the entity transaction.
    for prefix, count in (("ROM", room_count), ("MTR", meter_count), ("TEN", tenant_count)):
        connection.execute(
            sa.text("INSERT INTO identifier_counters (prefix, last_value) VALUES (:prefix, :last_value)"),
            {"prefix": prefix, "last_value": count},
        )

    # SQLite requires a batch table rebuild to enforce NOT NULL after backfill.
    with op.batch_alter_table("rooms") as batch:
        batch.alter_column("room_code", existing_type=sa.String(length=20), nullable=False)
    with op.batch_alter_table("meters") as batch:
        batch.alter_column("meter_code", existing_type=sa.String(length=20), nullable=False)

    op.create_index("ix_rooms_room_code", "rooms", ["room_code"], unique=True)
    op.create_index("ix_users_tenant_code", "users", ["tenant_code"], unique=True)
    op.create_index("ix_meters_meter_code", "meters", ["meter_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_meters_meter_code", table_name="meters")
    op.drop_index("ix_users_tenant_code", table_name="users")
    op.drop_index("ix_rooms_room_code", table_name="rooms")
    with op.batch_alter_table("meters") as batch:
        batch.drop_column("meter_code")
        batch.drop_column("is_active")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("tenant_code")
        batch.drop_column("is_active")
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("room_code")
        batch.drop_column("is_active")
    op.drop_table("identifier_counters")
