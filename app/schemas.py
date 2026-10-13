"""Pydantic request/response models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthRead(BaseModel):
    status: str = "ok"
    app: str
    environment: str


class RoomRead(ORMModel):
    id: int
    room_no: str


class MeterRead(ORMModel):
    id: int
    room_id: int
    current_balance: Decimal
    power_status: bool
    tariff_per_kwh: Decimal
    created_at: datetime


class PowerToggle(BaseModel):
    power_status: bool


class RechargeCreate(BaseModel):
    user_id: int
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    idempotency_key: str | None = Field(default=None, max_length=100)


class RechargeRead(ORMModel):
    id: int
    meter_id: int
    user_id: int
    amount: Decimal
    status: str
    idempotency_key: str | None
    created_at: datetime


class ReadingCreate(BaseModel):
    units_used: Decimal = Field(gt=0, max_digits=12, decimal_places=4)


class ReadingRead(ORMModel):
    id: int
    meter_id: int
    units_used: Decimal
    cost: Decimal
    balance_after: Decimal
    created_at: datetime


class DailyUsage(BaseModel):
    date: str
    units_used: Decimal
    cost: Decimal


class UsageReport(BaseModel):
    meter_id: int
    period: Literal["1d", "7d", "30d"]
    total_units: Decimal
    total_cost: Decimal
    reading_count: int
    daily: list[DailyUsage]


class TicketCreate(BaseModel):
    user_id: int
    issue_type: str = Field(min_length=2, max_length=50)
    description: str = Field(min_length=5, max_length=5000)


class TicketRead(ORMModel):
    id: int
    user_id: int
    issue_type: str
    description: str
    status: str
    created_at: datetime
