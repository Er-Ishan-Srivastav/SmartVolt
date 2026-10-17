"""Add ticket visibility, room snapshots, readable IDs, and threaded replies.

Revision ID: 0006_support_conversations
Revises: 0005_recharge_refs
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_support_conversations"
down_revision = "0005_recharge_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    naming_convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}

    with op.batch_alter_table("tickets", naming_convention=naming_convention) as batch:
        batch.add_column(sa.Column("ticket_code", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("room_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("room_code_snapshot", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("room_no_snapshot", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("visibility", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("priority", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_tickets_room_id_rooms", "rooms", ["room_id"], ["id"], ondelete="SET NULL"
        )

    # Normalize legacy labels into the explicit current workflow vocabulary.
    connection.execute(sa.text("UPDATE tickets SET status='IN_PROGRESS' WHERE UPPER(status) IN ('IN PROGRESS', 'IN-PROGRESS')"))
    connection.execute(sa.text("UPDATE tickets SET status='AWAITING_RESIDENT' WHERE UPPER(status) IN ('AWAITING RESIDENT', 'WAITING FOR RESIDENT')"))
    connection.execute(sa.text("UPDATE tickets SET status='RESOLVED' WHERE UPPER(status) IN ('RESOLVED', 'SOLVED')"))
    connection.execute(sa.text("UPDATE tickets SET status='CLOSED' WHERE UPPER(status)='CLOSED'"))
    connection.execute(sa.text("UPDATE tickets SET status='OPEN' WHERE UPPER(status) NOT IN ('OPEN', 'IN_PROGRESS', 'AWAITING_RESIDENT', 'RESOLVED', 'CLOSED')"))

    rows = connection.execute(sa.text(
        "SELECT t.id, t.user_id, t.description, t.created_at, u.name, u.role, "
        "r.id AS room_id, r.room_code, r.room_no "
        "FROM tickets t JOIN users u ON u.id = t.user_id "
        "LEFT JOIN rooms r ON r.id = u.room_id ORDER BY t.id"
    )).mappings().all()
    for sequence, row in enumerate(rows, start=1):
        room_id = row["room_id"]
        connection.execute(sa.text(
            "UPDATE tickets SET ticket_code=:code, room_id=:room_id, "
            "room_code_snapshot=:room_code, room_no_snapshot=:room_no, "
            "visibility=:visibility, priority='NORMAL', updated_at=:updated_at WHERE id=:id"
        ), {
            "code": f"TKT-{sequence:06d}",
            "room_id": room_id,
            "room_code": row["room_code"],
            "room_no": row["room_no"],
            # Existing roomless tickets are private by default to avoid widening access.
            "visibility": "ROOM" if room_id is not None else "PRIVATE",
            "updated_at": row["created_at"],
            "id": row["id"],
        })

    counter = connection.execute(sa.text(
        "SELECT prefix FROM identifier_counters WHERE prefix='TKT'"
    )).first()
    if counter:
        connection.execute(sa.text(
            "UPDATE identifier_counters SET last_value=:value WHERE prefix='TKT'"
        ), {"value": len(rows)})
    else:
        connection.execute(sa.text(
            "INSERT INTO identifier_counters (prefix, last_value) VALUES ('TKT', :value)"
        ), {"value": len(rows)})

    # Make newly added fields mandatory only after existing tickets have been backfilled.
    with op.batch_alter_table("tickets", naming_convention=naming_convention) as batch:
        batch.alter_column("ticket_code", existing_type=sa.String(length=20), nullable=False)
        batch.alter_column("visibility", existing_type=sa.String(length=12), nullable=False, server_default="ROOM")
        batch.alter_column("priority", existing_type=sa.String(length=12), nullable=False, server_default="NORMAL")
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())

    op.create_index("ix_tickets_ticket_code", "tickets", ["ticket_code"], unique=True)
    op.create_index("ix_tickets_room_visibility_created", "tickets", ["room_id", "visibility", "created_at"])

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(length=100), nullable=False),
        sa.Column("author_role", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ticket_messages_ticket_created", "ticket_messages", ["ticket_id", "created_at"])

    # Seed a first timeline message from each existing ticket's original description.
    # Author snapshots make the history readable even if the account later changes.
    for row in rows:
        connection.execute(sa.text(
            "INSERT INTO ticket_messages "
            "(ticket_id, author_user_id, author_name, author_role, message, created_at) "
            "VALUES (:ticket_id, :author_user_id, :author_name, :author_role, :message, :created_at)"
        ), {
            "ticket_id": row["id"],
            "author_user_id": row["user_id"],
            "author_name": row["name"] or "Resident",
            "author_role": row["role"] or "RESIDENT",
            "message": row["description"],
            "created_at": row["created_at"],
        })


def downgrade() -> None:
    op.drop_index("ix_ticket_messages_ticket_created", table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index("ix_tickets_room_visibility_created", table_name="tickets")
    op.drop_index("ix_tickets_ticket_code", table_name="tickets")
    naming_convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("tickets", naming_convention=naming_convention) as batch:
        batch.drop_column("updated_at")
        batch.drop_column("priority")
        batch.drop_column("visibility")
        batch.drop_column("room_no_snapshot")
        batch.drop_column("room_code_snapshot")
        batch.drop_column("room_id")
        batch.drop_column("ticket_code")
    op.get_bind().execute(sa.text("DELETE FROM identifier_counters WHERE prefix='TKT'"))
