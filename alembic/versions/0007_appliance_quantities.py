"""Add appliance quantities to the live simulation load board.

Revision ID: 0007_appliance_quantities
Revises: 0006_support_conversations
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_appliance_quantities"
down_revision = "0006_support_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing live loads represent one appliance each. The server default
    # preserves those rows when production databases are upgraded in place.
    op.add_column(
        "active_appliances",
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("active_appliances", "quantity")
