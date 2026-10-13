"""Initial SmartVolt relational schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_no", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rooms_room_no", "rooms", ["room_no"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("phone"),
    )

    op.create_table(
        "meters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_balance", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("power_status", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("tariff_per_kwh", sa.Numeric(10, 4), server_default="8.0000", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("room_id", name="uq_meters_room_id"),
    )

    op.create_table(
        "recharges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meter_id", sa.Integer(), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="SUCCESSFUL", nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_recharges_meter_created", "recharges", ["meter_id", "created_at"])

    op.create_table(
        "consumption_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meter_id", sa.Integer(), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("units_used", sa.Numeric(12, 4), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consumption_meter_created", "consumption_logs", ["meter_id", "created_at"])

    op.create_table(
        "wallet_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meter_id", sa.Integer(), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ledger_meter_created", "wallet_ledger", ["meter_id", "created_at"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tickets_user_created", "tickets", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tickets_user_created", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_ledger_meter_created", table_name="wallet_ledger")
    op.drop_table("wallet_ledger")
    op.drop_index("ix_consumption_meter_created", table_name="consumption_logs")
    op.drop_table("consumption_logs")
    op.drop_index("ix_recharges_meter_created", table_name="recharges")
    op.drop_table("recharges")
    op.drop_table("meters")
    op.drop_table("users")
    op.drop_index("ix_rooms_room_no", table_name="rooms")
    op.drop_table("rooms")
