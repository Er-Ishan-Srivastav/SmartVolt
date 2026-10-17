"""Relational models for rooms, tenants, prepaid meters and audit records."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, event, func, insert, select, true, update
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IdentifierCounter(Base):
    """Transactional sequences for permanent, human-readable public identifiers."""

    __tablename__ = "identifier_counters"

    prefix: Mapped[str] = mapped_column(String(3), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    room_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="room")
    meter: Mapped["Meter | None"] = relationship(back_populates="room", uselist=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_code: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(15), unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(60), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="RESIDENT", server_default="RESIDENT", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room | None] = relationship(back_populates="users")
    recharges: Mapped[list["Recharge"]] = relationship(back_populates="user", foreign_keys="Recharge.user_id")
    tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="user")


class Meter(Base):
    __tablename__ = "meters"
    __table_args__ = (UniqueConstraint("room_id", name="uq_meters_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    power_status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tariff_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("8.0000"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="meter")
    readings: Mapped[list["ConsumptionLog"]] = relationship(back_populates="meter")
    recharges: Mapped[list["Recharge"]] = relationship(back_populates="meter")
    ledger_entries: Mapped[list["WalletLedger"]] = relationship(back_populates="meter")


class Recharge(Base):
    __tablename__ = "recharges"
    __table_args__ = (
        Index("ix_recharges_meter_created", "meter_id", "created_at"),
        Index("ix_recharges_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recharge_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    # Optional tenant context/search target; not the person who performed the transaction.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESSFUL", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="recharges")
    user: Mapped[User | None] = relationship(back_populates="recharges", foreign_keys=[user_id])


class ConsumptionLog(Base):
    __tablename__ = "consumption_logs"
    __table_args__ = (Index("ix_consumption_meter_created", "meter_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    units_used: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="MANUAL", server_default="MANUAL", nullable=False)
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="readings")


class WalletLedger(Base):
    """Audit log: credits are positive, consumption debits are negative."""

    __tablename__ = "wallet_ledger"
    __table_args__ = (Index("ix_ledger_meter_created", "meter_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    # Legacy/optional tenant context; actor_user_id identifies who performed the change.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="ledger_entries")


class SupportTicket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_user_created", "user_id", "created_at"),
        Index("ix_tickets_room_visibility_created", "room_id", "visibility", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    room_code_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    room_no_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    visibility: Mapped[str] = mapped_column(String(12), default="ROOM", server_default="ROOM", nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", server_default="OPEN", nullable=False)
    priority: Mapped[str] = mapped_column(String(12), default="NORMAL", server_default="NORMAL", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="tickets")
    room: Mapped[Room | None] = relationship()
    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.created_at"
    )


class TicketMessage(Base):
    """Append-only support conversation message with author snapshots."""

    __tablename__ = "ticket_messages"
    __table_args__ = (Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(100), nullable=False)
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship()


class ActiveAppliance(Base):
    """Persisted appliance switches attached to a simulated meter."""

    __tablename__ = "active_appliances"
    __table_args__ = (UniqueConstraint("meter_id", "appliance_id", name="uq_active_appliance_meter_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False, index=True)
    appliance_id: Mapped[str] = mapped_column(String(40), nullable=False)
    appliance_name: Mapped[str] = mapped_column(String(100), nullable=False)
    watts: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    pending_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.000000"), server_default="0", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    meter: Mapped[Meter] = relationship()


class SimulationScenario(Base):
    """Built-in or user-authored daily appliance schedule."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (Index("ix_scenarios_audience_name", "audience", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner: Mapped[User | None] = relationship()


class AuthSession(Base):
    """Server-side session records make sign-out and password changes revoke tokens immediately."""

    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


def _allocate_public_code(connection, prefix: str) -> str:
    """Allocate a unique public identifier using a transactional database counter.

    Production databases get pre-populated counter rows from Alembic. The insert
    fallback supports fresh metadata-created test databases and local experiments.
    The increment and subsequent read occur in the same transaction. On PostgreSQL,
    UPDATE row locking serializes concurrent allocators; SQLite serializes writers.
    """
    table = IdentifierCounter.__table__
    result = connection.execute(
        update(table)
        .where(table.c.prefix == prefix)
        .values(last_value=table.c.last_value + 1)
    )
    if result.rowcount == 0:
        connection.execute(insert(table).values(prefix=prefix, last_value=1))
        sequence = 1
    else:
        selected = connection.execute(select(table.c.last_value).where(table.c.prefix == prefix))
        sequence = selected.scalar_one()
        selected.close()
    result.close()
    return f"{prefix}-{int(sequence):06d}"


@event.listens_for(Room, "before_insert")
def _assign_room_code(mapper, connection, target: Room) -> None:
    if not target.room_code:
        target.room_code = _allocate_public_code(connection, "ROM")


@event.listens_for(Meter, "before_insert")
def _assign_meter_code(mapper, connection, target: Meter) -> None:
    if not target.meter_code:
        target.meter_code = _allocate_public_code(connection, "MTR")


@event.listens_for(User, "before_insert")
def _assign_tenant_code(mapper, connection, target: User) -> None:
    if (target.role or "RESIDENT").upper() == "RESIDENT" and not target.tenant_code:
        target.tenant_code = _allocate_public_code(connection, "TEN")
    elif (target.role or "").upper() == "ADMIN":
        target.tenant_code = None


@event.listens_for(Recharge, "before_insert")
def _assign_recharge_code(mapper, connection, target: Recharge) -> None:
    if not target.recharge_code:
        target.recharge_code = _allocate_public_code(connection, "RCH")


@event.listens_for(SupportTicket, "before_insert")
def _assign_ticket_code(mapper, connection, target: SupportTicket) -> None:
    if not target.ticket_code:
        target.ticket_code = _allocate_public_code(connection, "TKT")
