"""Add demo authentication, active appliances, and reusable load scenarios.

Revision ID: 0002_simulation_and_auth
Revises: 0001_initial_schema
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_simulation_and_auth"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=60), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=20), server_default="RESIDENT", nullable=False))
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.add_column("consumption_logs", sa.Column("source", sa.String(length=30), server_default="MANUAL", nullable=False))
    op.add_column("consumption_logs", sa.Column("note", sa.String(length=250), nullable=True))

    op.create_table(
        "active_appliances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meter_id", sa.Integer(), sa.ForeignKey("meters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appliance_id", sa.String(length=40), nullable=False),
        sa.Column("appliance_name", sa.String(length=100), nullable=False),
        sa.Column("watts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("meter_id", "appliance_id", name="uq_active_appliance_meter_id"),
    )
    op.add_column("active_appliances", sa.Column("pending_kwh", sa.Numeric(12, 6), server_default="0", nullable=False))
    op.create_index("ix_active_appliances_meter_id", "active_appliances", ["meter_id"])

    op.create_table(
        "simulation_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_simulation_scenarios_slug", "simulation_scenarios", ["slug"], unique=True)
    op.create_index("ix_scenarios_audience_name", "simulation_scenarios", ["audience", "name"])


def downgrade() -> None:
    op.drop_index("ix_scenarios_audience_name", table_name="simulation_scenarios")
    op.drop_index("ix_simulation_scenarios_slug", table_name="simulation_scenarios")
    op.drop_table("simulation_scenarios")
    op.drop_index("ix_active_appliances_meter_id", table_name="active_appliances")
    op.drop_table("active_appliances")
    op.drop_column("consumption_logs", "note")
    op.drop_column("consumption_logs", "source")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
