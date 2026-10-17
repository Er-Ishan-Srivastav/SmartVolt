"""Pydantic request/response models."""

from datetime import date, datetime
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
    room_code: str
    room_no: str
    is_active: bool


class MeterRead(ORMModel):
    id: int
    meter_code: str
    is_active: bool
    room_id: int
    current_balance: Decimal
    power_status: bool
    tariff_per_kwh: Decimal
    created_at: datetime


class PowerToggle(BaseModel):
    power_status: bool


class RechargeCreate(BaseModel):
    # Legacy meter endpoint: residents may only name themselves; admins should use
    # the target-aware /admin/recharges endpoint instead.
    user_id: int | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    idempotency_key: str | None = Field(default=None, max_length=100)


class RechargeRead(ORMModel):
    id: int
    recharge_code: str
    meter_id: int
    user_id: int | None = None
    actor_user_id: int | None = None
    amount: Decimal
    status: str
    idempotency_key: str | None
    created_at: datetime


class RechargeTargetTenant(BaseModel):
    id: int
    tenant_code: str
    name: str
    username: str | None = None


class AdminRechargeTargetRead(BaseModel):
    meter_id: int
    meter_code: str
    room_id: int
    room_code: str
    room_no: str
    current_balance: Decimal
    tariff_per_kwh: Decimal
    tenants: list[RechargeTargetTenant] = Field(default_factory=list)


class AdminRechargeCreate(BaseModel):
    target_type: Literal["meter_id", "meter_code", "room_id", "room_code", "room_no", "tenant_id", "tenant_code", "username"]
    target_value: str = Field(min_length=1, max_length=100)
    tenant_context_id: int | None = Field(default=None, ge=1)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    idempotency_key: str | None = Field(default=None, max_length=100)


class AdminRechargeRead(BaseModel):
    id: int
    recharge_code: str
    meter_id: int
    meter_code: str
    room_id: int
    room_code: str
    room_no: str
    user_id: int | None = None
    tenant_code: str | None = None
    tenant_name: str | None = None
    actor_user_id: int | None = None
    actor_name: str | None = None
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


class HourlyUsage(BaseModel):
    hour: int = Field(ge=0, le=23)
    label: str
    units_used: Decimal
    cost: Decimal
    reading_count: int


class UsageReport(BaseModel):
    meter_id: int
    period: Literal["1d", "7d", "30d"]
    total_units: Decimal
    total_cost: Decimal
    reading_count: int
    daily: list[DailyUsage]
    granularity: Literal["daily", "hourly"] = "daily"
    timezone: str = "Asia/Kolkata"
    selected_date: date | None = None
    hourly: list[HourlyUsage] = Field(default_factory=list)
    # Older scenario simulations stored the full block total at its start time.
    # Those legacy totals remain in the day's totals but are not falsely assigned
    # to one hour; they are surfaced separately for data honesty.
    unallocated_units: Decimal = Decimal("0.0000")
    unallocated_cost: Decimal = Decimal("0.00")
    unallocated_reading_count: int = 0
    hourly_data_quality: Literal["RESOLVED", "COARSE_LEGACY", "MIXED", "NO_DATA"] = "NO_DATA"
    estimated_co2_kg: Decimal = Decimal("0.000")
    co2_factor_kg_per_kwh: Decimal = Decimal("0.675")
    co2_factor_source: str = ""
    co2_factor_source_url: str = "https://cea.nic.in/cdm-co2-baseline-database/?lang=en"
    tree_years_equivalent: Decimal = Decimal("0.0000")
    tree_absorption_kg_per_year: Decimal = Decimal("22.0")
    environmental_estimate_note: str = (
        "Estimated grid emissions only. Tree-year equivalent is illustrative and does not represent verified trees saved."
    )


class BillingStatementRead(BaseModel):
    meter_id: int
    meter_code: str
    room_code: str
    room_no: str
    month: str
    period_start: date
    period_end: date
    timezone: str = "Asia/Kolkata"
    current_tariff_per_kwh: Decimal
    total_units: Decimal
    total_energy_cost: Decimal
    total_recharge_amount: Decimal
    reading_count: int
    recharge_count: int
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    estimated_co2_kg: Decimal
    co2_factor_kg_per_kwh: Decimal
    co2_factor_source: str
    co2_factor_source_url: str
    statement_note: str = (
        "Consumption cost uses recorded reading costs. The displayed tariff is the meter's current tariff, "
        "not a reconstructed historic tariff schedule."
    )


class TicketCreate(BaseModel):
    # User identity is derived from the session. Optional field is retained for
    # backwards compatibility, but a mismatch is rejected by the API.
    user_id: int | None = Field(default=None, ge=1)
    issue_type: str = Field(min_length=2, max_length=50)
    description: str = Field(min_length=5, max_length=5000)
    visibility: Literal["ROOM", "PRIVATE"] = "ROOM"


class TicketMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class TicketMessageRead(ORMModel):
    id: int
    ticket_id: int
    author_user_id: int | None = None
    author_name: str
    author_role: Literal["ADMIN", "RESIDENT"]
    message: str
    created_at: datetime


class TicketStatusUpdate(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "AWAITING_RESIDENT", "RESOLVED", "CLOSED"] | None = None
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] | None = None


class TicketRead(ORMModel):
    id: int
    ticket_code: str
    user_id: int
    room_id: int | None = None
    room_code_snapshot: str | None = None
    room_no_snapshot: str | None = None
    visibility: Literal["ROOM", "PRIVATE"]
    issue_type: str
    description: str
    status: Literal["OPEN", "IN_PROGRESS", "AWAITING_RESIDENT", "RESOLVED", "CLOSED"]
    priority: str
    created_at: datetime
    updated_at: datetime
    requester_name: str | None = None
    requester_username: str | None = None
    messages: list[TicketMessageRead] = Field(default_factory=list)


class AdminTicketRead(TicketRead):
    requester_name: str
    requester_username: str | None = None
    room_no: str | None = None


class LoginCreate(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class AuthAccountRead(BaseModel):
    id: int
    name: str
    username: str
    role: Literal["ADMIN", "RESIDENT"]
    room_id: int | None = None
    tenant_code: str | None = None
    phone: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=15)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class LoginRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 28800
    account: AuthAccountRead


class AdminTenantRead(ORMModel):
    id: int
    tenant_code: str | None = None
    is_active: bool = True
    name: str
    username: str | None
    phone: str | None
    room_id: int | None
    role: str


class AdminRoomRead(ORMModel):
    id: int
    room_code: str
    is_active: bool
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
    quantity: int = Field(ge=1, le=100)
    started_at: datetime


class ApplianceToggle(BaseModel):
    enabled: bool
    quantity: int = Field(default=1, ge=1, le=100)


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
    # Missing quantity entries are interpreted as one unit for backwards
    # compatibility with scenarios stored before quantity controls existed.
    appliance_quantities: dict[str, int] = Field(default_factory=dict)


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
