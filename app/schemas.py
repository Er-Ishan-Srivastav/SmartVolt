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
    source: str = "MANUAL"
    note: str | None = None


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


class LoginCreate(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class AuthAccountRead(BaseModel):
    id: int
    name: str
    username: str
    role: Literal["ADMIN", "RESIDENT"]
    room_id: int | None = None


class LoginRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 28800
    account: AuthAccountRead


class AdminTenantRead(ORMModel):
    id: int
    name: str
    username: str | None
    phone: str | None
    room_id: int | None
    role: str


class AdminRoomRead(ORMModel):
    id: int
    room_no: str
    created_at: datetime
    meter: MeterRead | None = None
    tenants: list[AdminTenantRead] = []


class AdminRoomCreate(BaseModel):
    room_no: str = Field(min_length=1, max_length=20)
    tariff_per_kwh: Decimal = Field(default=Decimal("8.00"), gt=0, max_digits=10, decimal_places=4)
    opening_balance: Decimal = Field(default=Decimal("250.00"), ge=0, max_digits=12, decimal_places=2)
    first_tenant_name: str | None = Field(default=None, max_length=100)
    first_tenant_phone: str | None = Field(default=None, max_length=15)
    first_tenant_username: str | None = Field(default=None, min_length=3, max_length=60)
    first_tenant_password: str | None = Field(default=None, min_length=8, max_length=200)


class AdminRoomUpdate(BaseModel):
    room_no: str = Field(min_length=1, max_length=20)
    tariff_per_kwh: Decimal = Field(gt=0, max_digits=10, decimal_places=4)


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=200)
    phone: str | None = Field(default=None, max_length=15)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    username: str | None = Field(default=None, min_length=3, max_length=60)
    phone: str | None = Field(default=None, max_length=15)
    password: str | None = Field(default=None, min_length=8, max_length=200)


class ApplianceRead(BaseModel):
    id: str
    name: str
    watts: int
    category: str
    hint: str


class ActiveApplianceRead(ORMModel):
    id: int
    meter_id: int
    appliance_id: str
    appliance_name: str
    watts: int
    started_at: datetime


class ApplianceToggle(BaseModel):
    enabled: bool


class SimulationTickCreate(BaseModel):
    elapsed_seconds: Decimal = Field(gt=0, le=Decimal("86400"), max_digits=12, decimal_places=3)


class SimulationTickRead(BaseModel):
    meter: MeterRead
    live_watts: int
    reading: ReadingRead | None = None


class ScenarioBlock(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    start_min: int = Field(ge=0, lt=1440)
    end_min: int = Field(gt=0, le=1440)
    appliance_ids: list[str] = Field(min_length=1, max_length=10)


class ScenarioRead(ORMModel):
    id: int
    slug: str
    name: str
    audience: Literal["ADMIN", "RESIDENT"]
    description: str
    blocks: list[ScenarioBlock]
    is_builtin: bool
    owner_user_id: int | None
    created_at: datetime


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    audience: Literal["ADMIN", "RESIDENT"]
    description: str = Field(default="", max_length=500)
    blocks: list[ScenarioBlock] = Field(min_length=1, max_length=48)


class ScenarioApplyCreate(BaseModel):
    meter_id: int | None = None
    apply_all: bool = False
    simulation_date: str | None = None


class ScenarioApplyItem(BaseModel):
    meter_id: int
    room_id: int
    units_used: Decimal
    cost: Decimal
    reading_count: int
    partial: bool
    historical_only: bool


class ScenarioApplyRead(BaseModel):
    scenario_id: int
    simulation_date: str
    results: list[ScenarioApplyItem]
