"""Relational models for rooms, tenants, prepaid meters and audit records."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="room")
    meter: Mapped["Meter | None"] = relationship(back_populates="room", uselist=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(15), unique=True, nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room | None] = relationship(back_populates="users")
    recharges: Mapped[list["Recharge"]] = relationship(back_populates="user")
    tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="user")


class Meter(Base):
    __tablename__ = "meters"
    __table_args__ = (UniqueConstraint("room_id", name="uq_meters_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
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
    __table_args__ = (Index("ix_recharges_meter_created", "meter_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESSFUL", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="recharges")
    user: Mapped[User] = relationship(back_populates="recharges")


class ConsumptionLog(Base):
    __tablename__ = "consumption_logs"
    __table_args__ = (Index("ix_consumption_meter_created", "meter_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    units_used: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="readings")


class WalletLedger(Base):
    """Audit log: credits are positive, consumption debits are negative."""

    __tablename__ = "wallet_ledger"
    __table_args__ = (Index("ix_ledger_meter_created", "meter_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="ledger_entries")


class SupportTicket(Base):
    __tablename__ = "tickets"
    __table_args__ = (Index("ix_tickets_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="tickets")
