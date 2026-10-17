"""HTTP API endpoints for meters, wallet transactions, usage reports and tickets."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import csv
import io
import re
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.orm import Session, aliased, joinedload

from app.core import settings
from app.db.session import get_db
from app.models import ActiveAppliance, AuthSession, ConsumptionLog, Meter, Recharge, Room, SimulationScenario, SupportTicket, TicketMessage, User, WalletLedger
from app.schemas import (
    AdminTicketRead,
    DailyUsage,
    HourlyUsage,
    HealthRead,
    MeterRead,
    PowerToggle,
    ReadingCreate,
    ReadingRead,
    RechargeCreate,
    RechargeRead,
    AdminRechargeCreate,
    AdminRechargeRead,
    AdminRechargeTargetRead,
    RechargeTargetTenant,
    TicketCreate,
    TicketMessageCreate,
    TicketMessageRead,
    TicketStatusUpdate,
    TicketRead,
    ProfileUpdate, PasswordChange,
    UsageReport, BillingStatementRead,
    ActiveApplianceRead, AdminRoomCreate, AdminRoomRead, AdminRoomUpdate, AdminTenantRead, ApplianceRead, ApplianceToggle, AuthAccountRead, LoginCreate, LoginRead, ScenarioApplyCreate, ScenarioApplyItem, ScenarioApplyRead, ScenarioCreate, ScenarioRead, SimulationTickCreate, SimulationTickRead, TenantCreate, TenantUpdate,
)
from app.services.billing import consume_units, recharge_meter, set_power_status
from app.security import get_current_user, decode_access_token, hash_password, issue_access_token, require_admin, verify_password
from app.simulation import APPLIANCES, APPLIANCE_BY_ID

router = APIRouter()


@router.get("/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(app=settings.app_name, environment=settings.environment)


@router.get("/meters", response_model=list[MeterRead], tags=["meters"])
def list_meters(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[Meter]:
    """Administrators see all meters; residents see only their assigned room."""
    query = select(Meter).join(Room, Meter.room_id == Room.id).where(Meter.is_active.is_(True), Room.is_active.is_(True)).order_by(Meter.id)
    if current_user.role != "ADMIN":
        if current_user.room_id is None:
            return []
        query = query.where(Meter.room_id == current_user.room_id)
    return list(db.scalars(query.limit(limit)).all())


@router.get("/meters/{meter_id}", response_model=MeterRead, tags=["meters"])
def get_meter(
    meter_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Meter:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    return meter


@router.patch("/meters/{meter_id}/power", response_model=MeterRead, tags=["meters"])
def toggle_meter_power(
    meter_id: int, payload: PowerToggle, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Meter:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    return set_power_status(db, meter_id, payload.power_status)


@router.post(
    "/meters/{meter_id}/recharges",
    response_model=RechargeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["wallet"],
)
def create_recharge(
    meter_id: int, payload: RechargeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Recharge:
    """Legacy self-service recharge endpoint; administrators use /admin/recharges."""
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    if current_user.role == "ADMIN":
        target_user_id = payload.user_id
        if target_user_id is not None:
            target = db.get(User, target_user_id)
            if target is None or target.role != "RESIDENT" or not target.is_active:
                raise HTTPException(status_code=404, detail="Active tenant not found")
            if target.room_id != meter.room_id:
                raise HTTPException(status_code=403, detail="Selected tenant is not assigned to this meter's room")
        return recharge_meter(
            db, meter_id, target_user_id, payload.amount, payload.idempotency_key,
            actor_user_id=current_user.id, allow_empty_target=True,
        )
    if payload.user_id is not None and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Residents can recharge only their own account")
    if current_user.room_id != meter.room_id:
        raise HTTPException(status_code=403, detail="Residents can recharge only their own room's meter")
    return recharge_meter(
        db, meter_id, current_user.id, payload.amount, payload.idempotency_key,
        actor_user_id=current_user.id,
    )


@router.get("/meters/{meter_id}/recharges", response_model=list[RechargeRead], tags=["wallet"])
def list_recharges(
    meter_id: int,
    status_filter: Literal["SUCCESSFUL", "FAILED"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[Recharge]:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    query = select(Recharge).where(Recharge.meter_id == meter_id).order_by(Recharge.created_at.desc())
    if status_filter:
        query = query.where(Recharge.status == status_filter)
    return list(db.scalars(query.limit(limit)).all())


def _resolve_admin_recharge_target(db: Session, payload: AdminRechargeCreate) -> tuple[Meter, User | None]:
    """Resolve a search shortcut to one canonical active meter and optional tenant context."""
    target_value = payload.target_value.strip()
    meter: Meter | None = None
    tenant: User | None = None
    if payload.target_type in {"meter_id", "room_id", "tenant_id"}:
        try:
            numeric_id = int(target_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{payload.target_type} must be numeric") from exc
        if payload.target_type == "meter_id":
            meter = db.get(Meter, numeric_id)
        elif payload.target_type == "room_id":
            room = db.get(Room, numeric_id)
            meter = db.scalar(select(Meter).where(Meter.room_id == room.id)) if room else None
        else:
            tenant = db.get(User, numeric_id)
    elif payload.target_type == "meter_code":
        meter = db.scalar(select(Meter).where(func.lower(Meter.meter_code) == target_value.lower()))
    elif payload.target_type == "room_code":
        room = db.scalar(select(Room).where(func.lower(Room.room_code) == target_value.lower()))
        meter = db.scalar(select(Meter).where(Meter.room_id == room.id)) if room else None
    elif payload.target_type == "room_no":
        room = db.scalar(select(Room).where(func.lower(Room.room_no) == target_value.lower()))
        meter = db.scalar(select(Meter).where(Meter.room_id == room.id)) if room else None
    elif payload.target_type == "tenant_code":
        tenant = db.scalar(select(User).where(func.lower(User.tenant_code) == target_value.lower()))
    elif payload.target_type == "username":
        tenant = db.scalar(select(User).where(func.lower(User.username) == target_value.lower()))

    if tenant is not None:
        if tenant.role != "RESIDENT" or not tenant.is_active or tenant.room_id is None:
            raise HTTPException(status_code=404, detail="Active tenant with a current room assignment not found")
        meter = db.scalar(select(Meter).where(Meter.room_id == tenant.room_id))
    if meter is None:
        raise HTTPException(status_code=404, detail="Recharge target not found")
    if not meter.is_active or not meter.room.is_active:
        raise HTTPException(status_code=404, detail="Recharge target is archived or inactive")
    if tenant is not None and tenant.room_id != meter.room_id:
        raise HTTPException(status_code=409, detail="Tenant assignment changed while resolving the recharge target")
    return meter, tenant


@router.get("/admin/recharge-targets", response_model=list[AdminRechargeTargetRead], tags=["administration", "wallet"])
def admin_recharge_targets(
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    _: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[AdminRechargeTargetRead]:
    """Search active meters by meter/room identifiers or an assigned tenant."""
    statement = select(Meter).join(Room, Meter.room_id == Room.id).where(
        Meter.is_active.is_(True), Room.is_active.is_(True)
    )
    term = (query or "").strip()
    if term:
        pattern = f"%{term}%"
        tenant_match = select(User.id).where(
            User.room_id == Room.id,
            User.role == "RESIDENT",
            User.is_active.is_(True),
            or_(
                User.tenant_code.ilike(pattern), User.username.ilike(pattern), User.name.ilike(pattern),
                cast(User.id, String).ilike(pattern),
            ),
        ).exists()
        statement = statement.where(or_(
            Meter.meter_code.ilike(pattern), Room.room_code.ilike(pattern), Room.room_no.ilike(pattern),
            cast(Meter.id, String).ilike(pattern), cast(Room.id, String).ilike(pattern), tenant_match,
        ))
    statement = statement.options(joinedload(Meter.room).joinedload(Room.users)).order_by(Room.room_no).limit(limit)
    meters = list(db.scalars(statement).unique().all())
    results: list[AdminRechargeTargetRead] = []
    for meter in meters:
        tenants = [
            RechargeTargetTenant(id=user.id, tenant_code=user.tenant_code or f"TEN-LEGACY-{user.id}", name=user.name, username=user.username)
            for user in meter.room.users if user.role == "RESIDENT" and user.is_active
        ]
        results.append(AdminRechargeTargetRead(
            meter_id=meter.id, meter_code=meter.meter_code, room_id=meter.room_id,
            room_code=meter.room.room_code, room_no=meter.room.room_no,
            current_balance=meter.current_balance, tariff_per_kwh=meter.tariff_per_kwh, tenants=tenants,
        ))
    return results


@router.post("/admin/recharges", response_model=AdminRechargeRead, status_code=201, tags=["administration", "wallet"])
def admin_create_recharge(
    payload: AdminRechargeCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Create an admin-performed recharge against the resolved canonical meter."""
    meter, tenant = _resolve_admin_recharge_target(db, payload)
    if payload.tenant_context_id is not None:
        selected_tenant = db.get(User, payload.tenant_context_id)
        if (
            selected_tenant is None or selected_tenant.role != "RESIDENT"
            or not selected_tenant.is_active or selected_tenant.room_id != meter.room_id
        ):
            raise HTTPException(status_code=422, detail="Tenant context must be an active resident assigned to the selected meter's room")
        if tenant is not None and tenant.id != selected_tenant.id:
            raise HTTPException(status_code=422, detail="Tenant selector conflicts with the recharge target")
        tenant = selected_tenant
    recharge = recharge_meter(
        db, meter.id, tenant.id if tenant else None, payload.amount,
        payload.idempotency_key, actor_user_id=current_user.id, allow_empty_target=True,
    )
    return _admin_recharge_record(db, recharge)


def _admin_recharge_record(db: Session, recharge: Recharge) -> dict:
    target_user = db.get(User, recharge.user_id) if recharge.user_id is not None else None
    actor = db.get(User, recharge.actor_user_id) if recharge.actor_user_id is not None else None
    meter = db.get(Meter, recharge.meter_id)
    room = db.get(Room, meter.room_id) if meter else None
    return {
        "id": recharge.id, "recharge_code": recharge.recharge_code, "meter_id": recharge.meter_id,
        "meter_code": meter.meter_code if meter else "", "room_id": room.id if room else 0,
        "room_code": room.room_code if room else "", "room_no": room.room_no if room else "",
        "user_id": recharge.user_id, "tenant_code": target_user.tenant_code if target_user else None,
        "tenant_name": target_user.name if target_user else None,
        "actor_user_id": recharge.actor_user_id, "actor_name": actor.name if actor else None,
        "amount": recharge.amount, "status": recharge.status,
        "idempotency_key": recharge.idempotency_key, "created_at": recharge.created_at,
    }


@router.get("/admin/recharges", response_model=list[AdminRechargeRead], tags=["administration", "wallet"])
def admin_list_recharges(
    query: str | None = Query(default=None, max_length=100),
    status_filter: Literal["SUCCESSFUL", "FAILED"] | None = Query(default=None, alias="status"),
    meter_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[dict]:
    """List cross-room recharge history with target and actor attribution."""
    target_user = aliased(User)
    actor_user = aliased(User)
    statement = select(Recharge, Meter, Room, target_user, actor_user).join(
        Meter, Recharge.meter_id == Meter.id
    ).join(Room, Meter.room_id == Room.id).outerjoin(
        target_user, Recharge.user_id == target_user.id
    ).outerjoin(actor_user, Recharge.actor_user_id == actor_user.id)
    if status_filter:
        statement = statement.where(Recharge.status == status_filter)
    if meter_id is not None:
        statement = statement.where(Recharge.meter_id == meter_id)
    term = (query or "").strip()
    if term:
        pattern = f"%{term}%"
        statement = statement.where(or_(
            Recharge.recharge_code.ilike(pattern), Meter.meter_code.ilike(pattern),
            Room.room_code.ilike(pattern), Room.room_no.ilike(pattern),
            target_user.tenant_code.ilike(pattern), target_user.name.ilike(pattern),
            target_user.username.ilike(pattern), actor_user.name.ilike(pattern),
            actor_user.username.ilike(pattern),
        ))
    rows = db.execute(statement.order_by(Recharge.created_at.desc(), Recharge.id.desc()).limit(limit)).all()
    return [{
        "id": recharge.id, "recharge_code": recharge.recharge_code, "meter_id": recharge.meter_id,
        "meter_code": meter.meter_code, "room_id": room.id, "room_code": room.room_code,
        "room_no": room.room_no, "user_id": recharge.user_id,
        "tenant_code": target_user_row.tenant_code if target_user_row else None,
        "tenant_name": target_user_row.name if target_user_row else None,
        "actor_user_id": recharge.actor_user_id,
        "actor_name": actor_row.name if actor_row else None,
        "amount": recharge.amount, "status": recharge.status,
        "idempotency_key": recharge.idempotency_key, "created_at": recharge.created_at,
    } for recharge, meter, room, target_user_row, actor_row in rows]


@router.post(
    "/meters/{meter_id}/readings",
    response_model=ReadingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["simulation"],
)
def create_simulated_reading(
    meter_id: int, payload: ReadingCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ConsumptionLog:
    """Record simulated consumption for an authorized meter."""
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    reading = consume_units(db, meter_id, payload.units_used)
    if reading is None:
        raise HTTPException(status_code=409, detail="Meter is off or has no available balance")
    return reading


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingRead], tags=["usage"])
def list_readings(
    meter_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[ConsumptionLog]:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    query = (
        select(ConsumptionLog)
        .where(ConsumptionLog.meter_id == meter_id)
        .order_by(ConsumptionLog.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query).all())


def _environmental_report_fields(total_units: Decimal) -> dict:
    """Estimate grid CO2 from recorded kWh using explicit, configurable assumptions."""
    factor = Decimal(str(settings.grid_co2_factor_kg_per_kwh))
    tree_absorption = Decimal(str(settings.tree_co2_absorption_kg_per_year))
    estimated_co2 = (total_units * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    tree_years = (
        (estimated_co2 / tree_absorption).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if tree_absorption > 0 else Decimal("0.0000")
    )
    return {
        "estimated_co2_kg": estimated_co2,
        "co2_factor_kg_per_kwh": factor,
        "co2_factor_source": settings.grid_co2_factor_source,
        "co2_factor_source_url": settings.grid_co2_factor_source_url,
        "tree_years_equivalent": tree_years,
        "tree_absorption_kg_per_year": tree_absorption,
    }


def _utc_storage_timestamp(value: datetime) -> datetime:
    """Normalize SQLite-naive or timezone-aware timestamps using the UTC storage convention."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _csv_safe(value: object) -> str:
    """Neutralize spreadsheet formula prefixes in user-controlled CSV cells."""
    text_value = "" if value is None else str(value)
    if text_value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text_value
    return text_value


@router.get("/meters/{meter_id}/report", response_model=UsageReport, tags=["analytics"])
def consumption_report(
    meter_id: int,
    period: Literal["1d", "7d", "30d"] = "7d",
    granularity: Literal["daily", "hourly"] = "daily",
    report_date: date | None = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> UsageReport:
    """Return daily totals or a 24-bucket Asia/Kolkata hourly report.

    Legacy scenario records (SCENARIO/SCENARIO_HISTORY) were recorded as whole
    blocks at their start time. For hourly reports, keep them in the day totals
    but report them separately instead of assigning their entire block to one hour.
    """
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)

    india_tz = ZoneInfo("Asia/Kolkata")
    now_india = datetime.now(india_tz)
    if granularity == "hourly":
        selected_day = report_date or now_india.date()
        if selected_day > now_india.date():
            raise HTTPException(status_code=422, detail="Future dates cannot be analyzed")
        local_start = datetime.combine(selected_day, time.min, tzinfo=india_tz)
        local_end = local_start + timedelta(days=1)
        utc_start = local_start.astimezone(timezone.utc)
        utc_end = local_end.astimezone(timezone.utc)
        readings = list(db.scalars(
            select(ConsumptionLog)
            .where(
                ConsumptionLog.meter_id == meter_id,
                ConsumptionLog.created_at >= utc_start,
                ConsumptionLog.created_at < utc_end,
            )
            .order_by(ConsumptionLog.created_at, ConsumptionLog.id)
        ).all())

        def clock_label(hour_value: int) -> str:
            hour12 = hour_value % 12 or 12
            suffix = "AM" if hour_value < 12 else "PM"
            return f"{hour12} {suffix}"

        buckets = [{
            "hour": hour,
            "label": f"{clock_label(hour)}–{clock_label((hour + 1) % 24)}",
            "units_used": Decimal("0.0000"),
            "cost": Decimal("0.00"),
            "reading_count": 0,
        } for hour in range(24)]
        total_units = Decimal("0.0000")
        total_cost = Decimal("0.00")
        unallocated_units = Decimal("0.0000")
        unallocated_cost = Decimal("0.00")
        unallocated_count = 0
        resolved_count = 0
        # Older scenario rows represented a whole schedule block, not one hour.
        # The seeded demo HISTORICAL rows are daily totals stored at an arbitrary
        # clock time, so those are also coarse and must not be presented as hourly.
        coarse_sources = {"SCENARIO", "SCENARIO_HISTORY"}
        for reading in readings:
            units = Decimal(reading.units_used)
            cost = Decimal(reading.cost)
            total_units += units
            total_cost += cost
            is_seeded_daily_total = (
                reading.source == "HISTORICAL" and reading.note == "Seeded demo usage history"
            )
            if reading.source in coarse_sources or is_seeded_daily_total:
                unallocated_units += units
                unallocated_cost += cost
                unallocated_count += 1
                continue
            stamp = reading.created_at
            if stamp.tzinfo is None:
                # SQLite returns naive datetimes; stored naive timestamps follow
                # the app's existing UTC storage convention.
                stamp = stamp.replace(tzinfo=timezone.utc)
            hour = stamp.astimezone(india_tz).hour
            buckets[hour]["units_used"] += units
            buckets[hour]["cost"] += cost
            buckets[hour]["reading_count"] += 1
            resolved_count += 1

        if not readings:
            data_quality = "NO_DATA"
        elif unallocated_count and resolved_count:
            data_quality = "MIXED"
        elif unallocated_count:
            data_quality = "COARSE_LEGACY"
        else:
            data_quality = "RESOLVED"
        return UsageReport(
            meter_id=meter_id,
            period="1d",
            total_units=total_units,
            total_cost=total_cost,
            reading_count=len(readings),
            daily=[],
            granularity="hourly",
            timezone="Asia/Kolkata",
            selected_date=selected_day,
            hourly=[HourlyUsage(**row) for row in buckets],
            unallocated_units=unallocated_units,
            unallocated_cost=unallocated_cost,
            unallocated_reading_count=unallocated_count,
            hourly_data_quality=data_quality,
            **_environmental_report_fields(total_units),
        )

    # Daily views use the same India-local calendar and rolling period boundary as
    # hourly analytics, so the dashboard and the hour-by-hour view agree around midnight.
    now = datetime.now(india_tz)
    if period == "1d":
        local_start = datetime.combine(now.date(), time.min, tzinfo=india_tz)
        since = local_start.astimezone(timezone.utc)
    else:
        since = (now - timedelta(days={"7d": 7, "30d": 30}[period])).astimezone(timezone.utc)
    base_filter = (ConsumptionLog.meter_id == meter_id, ConsumptionLog.created_at >= since)
    aggregate = db.execute(
        select(
            func.coalesce(func.sum(ConsumptionLog.units_used), 0),
            func.coalesce(func.sum(ConsumptionLog.cost), 0),
            func.count(ConsumptionLog.id),
        ).where(*base_filter)
    ).one()
    # Create India-local calendar-day buckets using expressions compatible with both
    # supported databases. The schema stores timestamps in UTC by application convention.
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        day_expression = func.date(func.datetime(ConsumptionLog.created_at, "+5 hours", "+30 minutes"))
    elif dialect == "postgresql":
        day_expression = func.date(func.timezone("Asia/Kolkata", ConsumptionLog.created_at))
    else:
        # The project supports SQLite and PostgreSQL; refuse to silently label UTC days
        # as India-local if a different database is configured.
        raise HTTPException(status_code=500, detail="Daily local-time grouping is not configured for this database")
    daily_rows = db.execute(
        select(
            day_expression.label("usage_date"),
            func.coalesce(func.sum(ConsumptionLog.units_used), 0).label("units"),
            func.coalesce(func.sum(ConsumptionLog.cost), 0).label("cost"),
        )
        .where(*base_filter)
        .group_by(day_expression)
        .order_by(day_expression)
    ).all()
    daily = [
        DailyUsage(date=str(row.usage_date), units_used=Decimal(str(row.units)), cost=Decimal(str(row.cost)))
        for row in daily_rows
    ]
    return UsageReport(
        meter_id=meter_id,
        period=period,
        total_units=Decimal(str(aggregate[0])),
        total_cost=Decimal(str(aggregate[1])),
        reading_count=int(aggregate[2]),
        daily=daily,
        granularity="daily",
        timezone="Asia/Kolkata",
        **_environmental_report_fields(Decimal(str(aggregate[0]))),
    )


@router.get("/meters/{meter_id}/usage-export", tags=["analytics", "reports"])
def export_usage_csv(
    meter_id: int,
    start_date: date = Query(..., description="Inclusive start date in Asia/Kolkata"),
    end_date: date = Query(..., description="Inclusive end date in Asia/Kolkata"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    """Download itemized usage and cost rows for a date range of up to 366 days."""
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=422, detail="Exports are limited to 366 calendar days")

    india_tz = ZoneInfo("Asia/Kolkata")
    local_start = datetime.combine(start_date, time.min, tzinfo=india_tz)
    local_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=india_tz)
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)
    readings = list(db.scalars(
        select(ConsumptionLog)
        .where(
            ConsumptionLog.meter_id == meter_id,
            ConsumptionLog.created_at >= utc_start,
            ConsumptionLog.created_at < utc_end,
        )
        .order_by(ConsumptionLog.created_at, ConsumptionLog.id)
    ).all())
    room = meter.room
    total_units = sum((Decimal(row.units_used) for row in readings), Decimal("0.0000"))
    total_cost = sum((Decimal(row.cost) for row in readings), Decimal("0.00"))
    impact = _environmental_report_fields(total_units)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["SmartVolt consumption export"])
    writer.writerow(["Meter ID", _csv_safe(meter.meter_code)])
    writer.writerow(["Room ID", _csv_safe(room.room_code)])
    writer.writerow(["Room number", _csv_safe(room.room_no)])
    writer.writerow(["Period start (IST)", start_date.isoformat()])
    writer.writerow(["Period end (IST)", end_date.isoformat()])
    writer.writerow(["Current tariff (informational only, INR/kWh)", str(meter.tariff_per_kwh)])
    writer.writerow(["Recorded consumption (kWh)", f"{total_units:.4f}"])
    writer.writerow(["Recorded energy cost (INR)", f"{total_cost:.2f}"])
    writer.writerow(["Estimated grid CO2 (kg)", str(impact["estimated_co2_kg"])])
    writer.writerow(["Grid CO2 factor (kg/kWh)", str(impact["co2_factor_kg_per_kwh"])])
    writer.writerow(["CO2 factor source", impact["co2_factor_source"]])
    writer.writerow(["CO2 factor reference", impact["co2_factor_source_url"]])
    writer.writerow([])
    writer.writerow([
        "Reading ID", "Timestamp (Asia/Kolkata)", "Source", "Note",
        "Energy (kWh)", "Recorded cost (INR)", "Balance after (INR)",
    ])
    for reading in readings:
        stamp = _utc_storage_timestamp(reading.created_at).astimezone(india_tz).isoformat(timespec="seconds")
        writer.writerow([
            reading.id, stamp, _csv_safe(reading.source), _csv_safe(reading.note),
            f"{Decimal(reading.units_used):.4f}", f"{Decimal(reading.cost):.2f}",
            f"{Decimal(reading.balance_after):.2f}",
        ])
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", f"{len(readings)} reading(s)", f"{total_units:.4f}", f"{total_cost:.2f}", ""])
    safe_meter = re.sub(r"[^A-Za-z0-9_-]", "", meter.meter_code) or f"meter-{meter_id}"
    filename = f"smartvolt-usage-{safe_meter}-{start_date.isoformat()}-to-{end_date.isoformat()}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/meters/{meter_id}/billing-statement", response_model=BillingStatementRead, tags=["analytics", "reports"])
def monthly_billing_statement(
    meter_id: int,
    month: str = Query(..., min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$", description="Billing month as YYYY-MM"),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> BillingStatementRead:
    """Summarize a meter's recorded monthly consumption and recharges for a printable receipt."""
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    try:
        month_start = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="month must be a valid YYYY-MM month") from exc
    india_tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(india_tz).date()
    if month_start > today:
        raise HTTPException(status_code=422, detail="Future billing months are not available")
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    month_end = next_month - timedelta(days=1)
    local_start = datetime.combine(month_start, time.min, tzinfo=india_tz)
    local_end = datetime.combine(next_month, time.min, tzinfo=india_tz)
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    readings = list(db.scalars(select(ConsumptionLog).where(
        ConsumptionLog.meter_id == meter_id,
        ConsumptionLog.created_at >= utc_start,
        ConsumptionLog.created_at < utc_end,
    )).all())
    entries_in_month = list(db.scalars(select(WalletLedger).where(
        WalletLedger.meter_id == meter_id,
        WalletLedger.created_at >= utc_start,
        WalletLedger.created_at < utc_end,
    ).order_by(WalletLedger.created_at, WalletLedger.id)).all())
    prior_entry = db.scalar(select(WalletLedger).where(
        WalletLedger.meter_id == meter_id, WalletLedger.created_at < utc_start,
    ).order_by(WalletLedger.created_at.desc(), WalletLedger.id.desc()).limit(1))
    future_entry = db.scalar(select(WalletLedger).where(
        WalletLedger.meter_id == meter_id, WalletLedger.created_at >= utc_end,
    ).order_by(WalletLedger.created_at, WalletLedger.id).limit(1))
    first_entry = entries_in_month[0] if entries_in_month else None
    last_entry = entries_in_month[-1] if entries_in_month else None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    if prior_entry is not None:
        opening_balance = Decimal(prior_entry.balance_after)
    elif first_entry is not None:
        opening_balance = Decimal(first_entry.balance_after) - Decimal(first_entry.amount)
    if last_entry is not None:
        closing_balance = Decimal(last_entry.balance_after)
    elif prior_entry is not None:
        closing_balance = Decimal(prior_entry.balance_after)
    elif future_entry is not None:
        closing_balance = Decimal(future_entry.balance_after) - Decimal(future_entry.amount)
    total_units = sum((Decimal(row.units_used) for row in readings), Decimal("0.0000"))
    total_cost = sum((Decimal(row.cost) for row in readings), Decimal("0.00"))
    recharge_entries = [entry for entry in entries_in_month if entry.entry_type == "RECHARGE"]
    total_recharges = sum((Decimal(entry.amount) for entry in recharge_entries), Decimal("0.00"))
    impact = _environmental_report_fields(total_units)
    room = meter.room
    return BillingStatementRead(
        meter_id=meter.id, meter_code=meter.meter_code, room_code=room.room_code, room_no=room.room_no,
        month=month, period_start=month_start, period_end=month_end,
        current_tariff_per_kwh=meter.tariff_per_kwh, total_units=total_units,
        total_energy_cost=total_cost, total_recharge_amount=total_recharges,
        reading_count=len(readings), recharge_count=len(recharge_entries),
        opening_balance=opening_balance, closing_balance=closing_balance,
        estimated_co2_kg=impact["estimated_co2_kg"],
        co2_factor_kg_per_kwh=impact["co2_factor_kg_per_kwh"],
        co2_factor_source=impact["co2_factor_source"],
        co2_factor_source_url=impact["co2_factor_source_url"],
    )


def _ticket_payload(ticket: SupportTicket, *, admin_view: bool = False) -> dict:
    """Build a stable ticket response without exposing live account/room joins."""
    requester = ticket.user
    messages = sorted(ticket.messages, key=lambda message: (message.created_at, message.id))
    payload = {
        "id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "user_id": ticket.user_id,
        "room_id": ticket.room_id,
        "room_code_snapshot": ticket.room_code_snapshot,
        "room_no_snapshot": ticket.room_no_snapshot,
        "visibility": ticket.visibility,
        "issue_type": ticket.issue_type,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "requester_name": requester.name if requester else "Former resident",
        "requester_username": requester.username if requester else None,
        "messages": [
            {
                "id": message.id,
                "ticket_id": message.ticket_id,
                "author_user_id": message.author_user_id,
                "author_name": message.author_name,
                "author_role": message.author_role,
                "message": message.message,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }
    if admin_view:
        payload["room_no"] = ticket.room_no_snapshot
    return payload


def _can_access_ticket(ticket: SupportTicket, current_user: User) -> bool:
    if current_user.role == "ADMIN":
        return True
    if ticket.user_id == current_user.id:
        return True
    return (
        ticket.visibility == "ROOM"
        and current_user.room_id is not None
        and ticket.room_id == current_user.room_id
    )


def _load_ticket(db: Session, ticket_id: int) -> SupportTicket:
    ticket = db.execute(
        select(SupportTicket)
        .options(joinedload(SupportTicket.user), joinedload(SupportTicket.messages))
        .where(SupportTicket.id == ticket_id)
    ).unique().scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    return ticket


@router.post("/tickets", response_model=TicketRead, status_code=201, tags=["support"])
def create_ticket(
    payload: TicketCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Create a room-wide or private ticket; identity is always derived from the session."""
    if current_user.role != "RESIDENT":
        raise HTTPException(status_code=403, detail="Support tickets can only be created by resident accounts")
    if payload.user_id is not None and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Support tickets can only be submitted for the signed-in account")
    room = db.get(Room, current_user.room_id) if current_user.room_id is not None else None
    visibility = payload.visibility
    if visibility == "ROOM" and (room is None or not room.is_active):
        raise HTTPException(status_code=422, detail="Room-wide tickets require an active room assignment; choose a private ticket instead")
    ticket = SupportTicket(
        user_id=current_user.id,
        room_id=room.id if room else None,
        room_code_snapshot=room.room_code if room else None,
        room_no_snapshot=room.room_no if room else None,
        visibility=visibility if room else "PRIVATE",
        issue_type=payload.issue_type.strip(),
        description=payload.description.strip(),
        status="OPEN",
        priority="NORMAL",
    )
    db.add(ticket)
    db.flush()
    db.add(TicketMessage(
        ticket_id=ticket.id,
        author_user_id=current_user.id,
        author_name=current_user.name,
        author_role=current_user.role,
        message=payload.description.strip(),
    ))
    db.commit()
    ticket = _load_ticket(db, ticket.id)
    return _ticket_payload(ticket)


@router.get("/users/{user_id}/tickets", response_model=list[TicketRead], tags=["support"])
def list_user_tickets(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[dict]:
    """Residents see their own tickets plus room-wide tickets for their current room."""
    if user_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="You can view only your own support tickets")
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    criteria = [SupportTicket.user_id == user_id]
    if current_user.role != "ADMIN" and current_user.room_id is not None:
        criteria = [
            or_(
                SupportTicket.user_id == current_user.id,
                (SupportTicket.visibility == "ROOM") & (SupportTicket.room_id == current_user.room_id),
            )
        ]
    query = (
        select(SupportTicket)
        .options(joinedload(SupportTicket.user), joinedload(SupportTicket.messages))
        .where(*criteria)
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        .limit(limit)
    )
    return [_ticket_payload(ticket) for ticket in db.scalars(query).unique().all()]


@router.get("/tickets/{ticket_id}", response_model=TicketRead, tags=["support"])
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    ticket = _load_ticket(db, ticket_id)
    if not _can_access_ticket(ticket, current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this support ticket")
    return _ticket_payload(ticket, admin_view=current_user.role == "ADMIN")


@router.post("/tickets/{ticket_id}/messages", response_model=TicketMessageRead, status_code=201, tags=["support"])
def add_ticket_message(
    ticket_id: int,
    payload: TicketMessageCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TicketMessage:
    ticket = _load_ticket(db, ticket_id)
    if not _can_access_ticket(ticket, current_user):
        raise HTTPException(status_code=403, detail="You do not have access to this support ticket")
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if ticket.status == "CLOSED":
        raise HTTPException(status_code=409, detail="This ticket is closed. An administrator must reopen it before new replies can be added.")
    message = TicketMessage(
        ticket_id=ticket.id,
        author_user_id=current_user.id,
        author_name=current_user.name,
        author_role=current_user.role,
        message=message_text,
    )
    if current_user.role != "ADMIN":
        if ticket.status == "RESOLVED":
            # A resident reply to a resolved ticket requests that it be reopened.
            ticket.status = "OPEN"
        elif ticket.status == "AWAITING_RESIDENT":
            ticket.status = "IN_PROGRESS"
    elif ticket.status == "OPEN":
        ticket.status = "IN_PROGRESS"
    ticket.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.patch("/admin/tickets/{ticket_id}", response_model=AdminTicketRead, tags=["support"])
def update_support_ticket(
    ticket_id: int,
    payload: TicketStatusUpdate,
    current_user: User = Depends(require_admin), db: Session = Depends(get_db),
) -> dict:
    ticket = _load_ticket(db, ticket_id)
    if payload.status is None and payload.priority is None:
        raise HTTPException(status_code=422, detail="Provide a status or priority change")
    if payload.status in {"RESOLVED", "CLOSED"}:
        has_admin_response = any(message.author_role == "ADMIN" for message in ticket.messages)
        if not has_admin_response:
            raise HTTPException(status_code=409, detail="Send an administrator response before resolving or closing this ticket")
    if payload.status is not None:
        ticket.status = payload.status
    if payload.priority is not None:
        ticket.priority = payload.priority
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    ticket = _load_ticket(db, ticket.id)
    return _ticket_payload(ticket, admin_view=True)


@router.get("/admin/tickets", response_model=list[AdminTicketRead], tags=["support"])
def list_all_support_tickets(
    limit: int = Query(default=100, ge=1, le=200),
    status_filter: Literal["OPEN", "IN_PROGRESS", "AWAITING_RESIDENT", "RESOLVED", "CLOSED"] | None = Query(default=None, alias="status"),
    visibility: Literal["ROOM", "PRIVATE"] | None = Query(default=None),
    bucket: Literal["PENDING", "CLOSED"] | None = Query(default=None),
    _: User = Depends(require_admin), db: Session = Depends(get_db),
) -> list[dict]:
    """Return filtered support requests for administrator triage, including historical closed tickets."""
    query = (
        select(SupportTicket)
        .options(joinedload(SupportTicket.user), joinedload(SupportTicket.messages))
    )
    if status_filter:
        query = query.where(SupportTicket.status == status_filter)
    if bucket == "PENDING":
        query = query.where(SupportTicket.status.in_(["OPEN", "IN_PROGRESS", "AWAITING_RESIDENT"]))
    elif bucket == "CLOSED":
        query = query.where(SupportTicket.status.in_(["RESOLVED", "CLOSED"]))
    if visibility:
        query = query.where(SupportTicket.visibility == visibility)
    query = query.order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc()).limit(limit)
    return [_ticket_payload(ticket, admin_view=True) for ticket in db.scalars(query).unique().all()]


@router.get("/admin/tickets/summary", tags=["support"])
def admin_support_ticket_summary(
    _: User = Depends(require_admin), db: Session = Depends(get_db),
) -> dict[str, int]:
    """Count pending and completed tickets across all history for the administrator tabs."""
    pending = db.scalar(select(func.count()).select_from(SupportTicket).where(
        SupportTicket.status.in_(["OPEN", "IN_PROGRESS", "AWAITING_RESIDENT"])
    )) or 0
    closed = db.scalar(select(func.count()).select_from(SupportTicket).where(
        SupportTicket.status.in_(["RESOLVED", "CLOSED"])
    )) or 0
    return {"pending": int(pending), "closed": int(closed)}


# ---------------------------------------------------------------------------
# Authentication and administration. All account-specific APIs require a valid session;
# administrator mutations additionally require the ADMIN role.
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=LoginRead, tags=["authentication"])
def login(payload: LoginCreate, db: Session = Depends(get_db)) -> LoginRead:
    user = db.scalar(select(User).where(func.lower(User.username) == payload.username.strip().lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        # Keep the error generic to avoid exposing whether a username exists.
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    if not user.username:
        raise HTTPException(status_code=401, detail="This account is not configured for sign-in")
    access_token = issue_access_token(user, db)
    db.commit()
    return LoginRead(
        access_token=access_token,
        account=AuthAccountRead(id=user.id, name=user.name, username=user.username, role=user.role, room_id=user.room_id, tenant_code=user.tenant_code, phone=user.phone),
    )


@router.post("/auth/logout", tags=["authentication"])
def logout(request: Request, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    """Revoke the current token on the server so it cannot be reused after sign-out."""
    raw = request.headers.get("authorization", "")
    token = raw.partition(" ")[2] if raw.lower().startswith("bearer ") else ""
    claims = decode_access_token(token) if token else None
    if claims:
        session = db.get(AuthSession, claims["sid"])
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
    return {"success": True}


@router.get("/auth/me", response_model=AuthAccountRead, tags=["authentication"])
def who_am_i(user: User = Depends(get_current_user)) -> AuthAccountRead:
    return AuthAccountRead(id=user.id, name=user.name, username=user.username or "", role=user.role, room_id=user.room_id, tenant_code=user.tenant_code, phone=user.phone)


@router.patch("/auth/profile", response_model=AuthAccountRead, tags=["authentication"])
def update_my_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthAccountRead:
    """Update the signed-in user's own display name and contact number."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide a name or phone number to update")

    if "name" in updates:
        name = (updates["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        current_user.name = name

    if "phone" in updates:
        raw_phone = updates["phone"]
        phone = raw_phone.strip() if isinstance(raw_phone, str) else None
        phone = phone or None
        if phone is not None and db.scalar(select(User).where(User.phone == phone, User.id != current_user.id)):
            raise HTTPException(status_code=409, detail="That contact number is already associated with another account")
        current_user.phone = phone

    db.commit()
    db.refresh(current_user)
    return AuthAccountRead(
        id=current_user.id, name=current_user.name, username=current_user.username or "",
        role=current_user.role, room_id=current_user.room_id,
        tenant_code=current_user.tenant_code, phone=current_user.phone,
    )


@router.post("/auth/change-password", tags=["authentication"])
def change_my_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool | int]:
    """Change the signed-in user's password and revoke every active session."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(status_code=422, detail="Choose a password different from the current password")

    current_user.password_hash = hash_password(payload.new_password)
    revoked_at = datetime.now(timezone.utc)
    sessions = list(db.scalars(select(AuthSession).where(
        AuthSession.user_id == current_user.id, AuthSession.revoked_at.is_(None)
    )).all())
    for session in sessions:
        session.revoked_at = revoked_at
    db.commit()
    return {"success": True, "sessions_revoked": len(sessions)}


def _assert_meter_access(meter: Meter, current_user: User) -> None:
    """Residents may operate only active meters belonging to an active room."""
    if not meter.is_active or not meter.room.is_active:
        raise HTTPException(status_code=404, detail="Meter not found")
    if current_user.role != "ADMIN" and meter.room_id != current_user.room_id:
        raise HTTPException(status_code=403, detail="Residents can access only their own room's meter")


def _admin_room_read(room: Room) -> AdminRoomRead:
    tenants = [
        AdminTenantRead(
            id=user.id, tenant_code=user.tenant_code, is_active=user.is_active,
            name=user.name, username=user.username, phone=user.phone, room_id=user.room_id, role=user.role,
        )
        for user in room.users if user.role == "RESIDENT" and user.is_active
    ]
    return AdminRoomRead(
        id=room.id, room_code=room.room_code, is_active=room.is_active,
        room_no=room.room_no, created_at=room.created_at, meter=room.meter, tenants=tenants,
    )


@router.get("/admin/rooms", response_model=list[AdminRoomRead], tags=["administration"])
def admin_list_rooms(
    include_archived: bool = Query(default=False),
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[AdminRoomRead]:
    query = select(Room).order_by(Room.room_no)
    if not include_archived:
        query = query.where(Room.is_active.is_(True))
    rooms = list(db.scalars(query).all())
    return [_admin_room_read(room) for room in rooms]


@router.post("/admin/rooms", response_model=AdminRoomRead, status_code=201, tags=["administration"])
def admin_create_room(
    payload: AdminRoomCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminRoomRead:
    room_no = payload.room_no.strip()
    if not room_no:
        raise HTTPException(status_code=422, detail="Room number cannot be blank")
    if db.scalar(select(Room).where(func.lower(Room.room_no) == room_no.lower())):
        raise HTTPException(status_code=409, detail="That room number already exists")
    tenant_fields = [payload.first_tenant_name, payload.first_tenant_username, payload.first_tenant_password]
    if any(tenant_fields) and not all(tenant_fields):
        raise HTTPException(status_code=422, detail="When adding the first tenant, provide name, username and password")
    if payload.first_tenant_username and db.scalar(select(User).where(func.lower(User.username) == payload.first_tenant_username.lower())):
        raise HTTPException(status_code=409, detail="That username is already in use")
    if payload.first_tenant_phone and db.scalar(select(User).where(User.phone == payload.first_tenant_phone)):
        raise HTTPException(status_code=409, detail="That phone number is already assigned")

    room = Room(room_no=room_no)
    db.add(room)
    db.flush()
    meter = Meter(
        room_id=room.id,
        current_balance=payload.opening_balance,
        power_status=payload.opening_balance > 0,
        tariff_per_kwh=payload.tariff_per_kwh,
    )
    db.add(meter)
    db.flush()
    db.add(WalletLedger(
        meter_id=meter.id, user_id=None, entry_type="OPENING_BALANCE",
        amount=payload.opening_balance, balance_after=payload.opening_balance,
        reference_type="ROOM_CREATE", reference_id=room.id, actor_user_id=current_user.id,
    ))
    if all(tenant_fields):
        db.add(User(
            name=payload.first_tenant_name.strip(), phone=payload.first_tenant_phone or None,
            username=payload.first_tenant_username.strip(), password_hash=hash_password(payload.first_tenant_password),
            role="RESIDENT", room_id=room.id,
        ))
    db.commit()
    created = db.scalar(select(Room).where(Room.id == room.id))
    return _admin_room_read(created)


@router.patch("/admin/rooms/{room_id}", response_model=AdminRoomRead, tags=["administration"])
def admin_update_room(
    room_id: int,
    payload: AdminRoomUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminRoomRead:
    room = db.get(Room, room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=404, detail="Active room not found")

    room_no = payload.room_no.strip()
    if not room_no:
        raise HTTPException(status_code=422, detail="Room number cannot be blank")
    duplicate = db.scalar(
        select(Room).where(func.lower(Room.room_no) == room_no.lower(), Room.id != room_id)
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="That room number already exists")

    room.room_no = room_no
    if room.meter is not None:
        room.meter.tariff_per_kwh = payload.tariff_per_kwh
    db.commit()
    refreshed = db.scalar(select(Room).where(Room.id == room_id))
    return _admin_room_read(refreshed)


@router.delete("/admin/rooms/{room_id}", tags=["administration"])
def admin_archive_room(
    room_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Archive an empty room without deleting financial, meter, or usage history."""
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room.is_active:
        return {"message": f"Room {room.room_code} is already archived."}

    active_tenant = db.scalar(
        select(User.id).where(
            User.room_id == room_id, User.role == "RESIDENT", User.is_active.is_(True)
        ).limit(1)
    )
    if active_tenant is not None:
        raise HTTPException(
            status_code=409,
            detail="Move or deactivate all active tenants before archiving this room",
        )

    room.is_active = False
    if room.meter is not None:
        room.meter.is_active = False
        room.meter.power_status = False
        # Running appliances represent current simulated state, not history.
        db.execute(delete(ActiveAppliance).where(ActiveAppliance.meter_id == room.meter.id))
    db.commit()
    return {"message": f"Room {room.room_code} archived. Meter, balance, usage, recharge, and ledger history were preserved."}


@router.post("/admin/rooms/{room_id}/restore", response_model=AdminRoomRead, tags=["administration"])
def admin_restore_room(
    room_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminRoomRead:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.meter is None:
        raise HTTPException(status_code=409, detail="This room has no meter to restore")
    room.is_active = True
    room.meter.is_active = True
    room.meter.power_status = room.meter.current_balance > 0
    db.commit()
    db.refresh(room)
    return _admin_room_read(room)


@router.post("/admin/rooms/{room_id}/tenants", response_model=AdminTenantRead, status_code=201, tags=["administration"])
def admin_add_tenant(
    room_id: int,
    payload: TenantCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminTenantRead:
    room = db.get(Room, room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=404, detail="Active room not found")
    username = payload.username.strip()
    name = payload.name.strip()
    if not username or not name:
        raise HTTPException(status_code=422, detail="Name and username cannot be blank")
    if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
        raise HTTPException(status_code=409, detail="That username is already in use")
    if payload.phone and db.scalar(select(User).where(User.phone == payload.phone)):
        raise HTTPException(status_code=409, detail="That phone number is already assigned")
    tenant = User(
        name=name, username=username, password_hash=hash_password(payload.password),
        phone=payload.phone or None, role="RESIDENT", room_id=room_id,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return AdminTenantRead(id=tenant.id, tenant_code=tenant.tenant_code, is_active=tenant.is_active, name=tenant.name, username=tenant.username, phone=tenant.phone, room_id=tenant.room_id, role=tenant.role)


@router.get("/simulation/appliances", response_model=list[ApplianceRead], tags=["simulation"])
def list_appliances(_: User = Depends(get_current_user)) -> list[dict]:
    return APPLIANCES


@router.patch("/admin/tenants/{tenant_id}", response_model=AdminTenantRead, tags=["administration"])
def admin_update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminTenantRead:
    tenant = db.get(User, tenant_id)
    if tenant is None or not tenant.is_active or tenant.role != "RESIDENT" or tenant.room_id is None or not tenant.username:
        raise HTTPException(status_code=404, detail="Active tenant not found")
    changes = payload.model_fields_set
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one tenant field to update")

    if "name" in changes:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
        tenant.name = name
    if "username" in changes:
        username = (payload.username or "").strip()
        if not username:
            raise HTTPException(status_code=422, detail="Username cannot be blank")
        duplicate = db.scalar(
            select(User).where(func.lower(User.username) == username.lower(), User.id != tenant_id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="That username is already in use")
        tenant.username = username
    if "phone" in changes:
        phone = (payload.phone or "").strip() or None
        if phone:
            duplicate_phone = db.scalar(select(User).where(User.phone == phone, User.id != tenant_id))
            if duplicate_phone:
                raise HTTPException(status_code=409, detail="That phone number is already assigned")
        tenant.phone = phone
    if payload.password:
        tenant.password_hash = hash_password(payload.password)
        # Password resets revoke every existing tenant session immediately.
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id == tenant.id, AuthSession.revoked_at.is_(None))).all():
            session.revoked_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(tenant)
    return AdminTenantRead(
        id=tenant.id, tenant_code=tenant.tenant_code, is_active=tenant.is_active,
        name=tenant.name, username=tenant.username, phone=tenant.phone,
        room_id=tenant.room_id, role=tenant.role,
    )


@router.delete("/admin/tenants/{tenant_id}", tags=["administration"])
def admin_delete_tenant(
    tenant_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    tenant = db.get(User, tenant_id)
    if tenant is None or not tenant.is_active or tenant.role != "RESIDENT" or tenant.room_id is None or not tenant.username:
        raise HTTPException(status_code=404, detail="Active tenant not found")

    # Keep the underlying user row so billing records and support tickets retain
    # their foreign-key identity. Removing the tenant revokes login and unassigns
    # the room; the name remains available for historical records.
    tenant.room_id = None
    tenant.is_active = False
    tenant.username = None
    tenant.password_hash = None
    tenant.phone = None
    for session in db.scalars(
        select(AuthSession).where(AuthSession.user_id == tenant.id, AuthSession.revoked_at.is_(None))
    ).all():
        session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Tenant removed from the room; sign-in disabled and historical records preserved."}


@router.get("/simulation/scenarios", response_model=list[ScenarioRead], tags=["simulation"])
def list_scenarios(
    audience: Literal["ADMIN", "RESIDENT"] = "RESIDENT",
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[SimulationScenario]:
    if audience == "ADMIN" and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator sign-in is required for admin templates")
    query = select(SimulationScenario).where(SimulationScenario.audience == audience)
    query = query.where((SimulationScenario.is_builtin.is_(True)) | (SimulationScenario.owner_user_id == current_user.id))
    return list(db.scalars(query.order_by(SimulationScenario.is_builtin.desc(), SimulationScenario.name)).all())


@router.post("/simulation/scenarios", response_model=ScenarioRead, status_code=201, tags=["simulation"])
def create_scenario(
    payload: ScenarioCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SimulationScenario:
    if payload.audience == "ADMIN" and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only an administrator can save admin-wide templates")
    from app.simulation import APPLIANCE_BY_ID
    for item in payload.blocks:
        if item.end_min <= item.start_min:
            raise HTTPException(status_code=422, detail=f"Block '{item.label}' must end after it starts")
        unknown = set(item.appliance_ids) - APPLIANCE_BY_ID.keys()
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown appliances: {', '.join(sorted(unknown))}")
        unknown_quantity_ids = set(item.appliance_quantities) - set(item.appliance_ids)
        if unknown_quantity_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Quantities were provided for appliances not in block '{item.label}': {', '.join(sorted(unknown_quantity_ids))}",
            )
        invalid_quantities = {
            appliance_id: quantity
            for appliance_id, quantity in item.appliance_quantities.items()
            if quantity < 1 or quantity > 100
        }
        if invalid_quantities:
            raise HTTPException(status_code=422, detail="Appliance quantities must be between 1 and 100")
    base = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")[:55] or "custom"
    slug = f"custom-{current_user.id}-{base}"
    suffix = 2
    original = slug
    while db.scalar(select(SimulationScenario).where(SimulationScenario.slug == slug)):
        slug = f"{original}-{suffix}"
        suffix += 1
    scenario = SimulationScenario(
        slug=slug, name=payload.name.strip(), audience=payload.audience,
        description=payload.description.strip(), blocks=[item.model_dump() for item in payload.blocks],
        is_builtin=False, owner_user_id=current_user.id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.get("/meters/{meter_id}/simulation/appliances", response_model=list[ActiveApplianceRead], tags=["simulation"])
def list_active_appliances(
    meter_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ActiveAppliance]:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    return list(db.scalars(select(ActiveAppliance).where(ActiveAppliance.meter_id == meter_id).order_by(ActiveAppliance.appliance_name)).all())


@router.put("/meters/{meter_id}/simulation/appliances/{appliance_id}", response_model=list[ActiveApplianceRead], tags=["simulation"])
def set_appliance(
    meter_id: int, appliance_id: str, payload: ApplianceToggle,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ActiveAppliance]:
    appliance = APPLIANCE_BY_ID.get(appliance_id)
    if appliance is None:
        raise HTTPException(status_code=404, detail="Appliance not found")
    meter = db.scalar(select(Meter).where(Meter.id == meter_id).with_for_update())
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    existing = db.scalar(select(ActiveAppliance).where(ActiveAppliance.meter_id == meter_id, ActiveAppliance.appliance_id == appliance_id))
    if payload.enabled:
        if not meter.power_status or meter.current_balance <= 0:
            raise HTTPException(status_code=409, detail="Turn room power on and ensure the prepaid balance is positive first")
        if existing is None:
            db.add(ActiveAppliance(
                meter_id=meter_id, appliance_id=appliance_id,
                appliance_name=appliance["name"], watts=appliance["watts"],
                quantity=payload.quantity,
            ))
        else:
            existing.quantity = payload.quantity
    elif existing is not None:
        db.delete(existing)
    db.commit()
    return list(db.scalars(select(ActiveAppliance).where(ActiveAppliance.meter_id == meter_id).order_by(ActiveAppliance.appliance_name)).all())


@router.post("/meters/{meter_id}/simulation/tick", response_model=SimulationTickRead, tags=["simulation"])
def simulation_tick(
    meter_id: int, payload: SimulationTickCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SimulationTickRead:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    _assert_meter_access(meter, current_user)
    loads = list(db.scalars(select(ActiveAppliance).where(ActiveAppliance.meter_id == meter_id)).all())
    live_watts = sum(item.watts * item.quantity for item in loads)
    reading = None
    if live_watts > 0 and meter.power_status and meter.current_balance > 0:
        # Preserve sub-milli-kWh fractions between ticks so low-watt appliances
        # still bill accurately in real-time mode instead of disappearing in rounding.
        total_pending = Decimal("0")
        for load in loads:
            load.pending_kwh = Decimal(load.pending_kwh) + (
                Decimal(load.watts * load.quantity) * payload.elapsed_seconds / Decimal("3600000")
            )
            total_pending += Decimal(load.pending_kwh)
        if total_pending >= Decimal("0.001"):
            units = total_pending.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            names = ", ".join(
                f"{item.appliance_name} × {item.quantity}" if item.quantity > 1 else item.appliance_name
                for item in loads
            )
            if units > 0:
                reading = consume_units(db, meter_id, units, source="LIVE", note=f"Live appliances: {names}")
                if reading is not None:
                    for load in loads:
                        load.pending_kwh = Decimal("0.000000")
                    db.commit()
                    db.refresh(reading)
        else:
            db.commit()
    fresh_meter = db.get(Meter, meter_id)
    if fresh_meter.current_balance <= 0 or not fresh_meter.power_status:
        db.query(ActiveAppliance).filter(ActiveAppliance.meter_id == meter_id).delete(synchronize_session=False)
        db.commit()
        live_watts = 0
    return SimulationTickRead(meter=fresh_meter, live_watts=live_watts, reading=reading)


def _hour_segments(start_minute: int, end_minute: int) -> list[tuple[int, int]]:
    """Split a scenario's minute range at local hour boundaries."""
    segments: list[tuple[int, int]] = []
    cursor = start_minute
    while cursor < end_minute:
        next_hour = min(end_minute, ((cursor // 60) + 1) * 60)
        if next_hour <= cursor:
            next_hour = min(end_minute, cursor + 60)
        segments.append((cursor, next_hour))
        cursor = next_hour
    return segments


def _distribute_block_units(
    units: Decimal, cost: Decimal, segments: list[tuple[int, int]],
) -> list[tuple[int, Decimal, Decimal]]:
    """Allocate exact block totals across hourly segments without losing kWh/cost."""
    duration = sum(end - start for start, end in segments)
    unit_allocations: list[tuple[int, Decimal]] = []
    remaining_units = units
    for index, (start_minute, end_minute) in enumerate(segments):
        if index == len(segments) - 1:
            segment_units = remaining_units
        else:
            segment_units = (units * Decimal(end_minute - start_minute) / Decimal(duration)).quantize(
                Decimal("0.0001"), rounding=ROUND_DOWN
            )
            remaining_units -= segment_units
        if segment_units > 0:
            unit_allocations.append((start_minute, segment_units))

    if not unit_allocations:
        return []
    total_allocated_units = sum((value for _, value in unit_allocations), Decimal("0.0000"))
    # The last non-zero segment owns any rounding residual so the exact block kWh
    # total is conserved even if an early tiny segment rounds down to zero.
    last_start, last_units = unit_allocations[-1]
    unit_allocations[-1] = (last_start, last_units + (units - total_allocated_units))

    results: list[tuple[int, Decimal, Decimal]] = []
    allocated_cost = Decimal("0.00")
    for index, (start_minute, segment_units) in enumerate(unit_allocations):
        if index == len(unit_allocations) - 1:
            segment_cost = cost - allocated_cost
        else:
            segment_cost = (cost * segment_units / units).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            allocated_cost += segment_cost
        results.append((start_minute, segment_units, segment_cost))
    return results


def _apply_scenario_to_meter(db: Session, meter_id: int, scenario: SimulationScenario, day: date) -> ScenarioApplyItem:
    meter = db.scalar(select(Meter).where(Meter.id == meter_id).with_for_update())
    if meter is None:
        raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")
    tariff = Decimal(meter.tariff_per_kwh)
    india_tz = ZoneInfo("Asia/Kolkata")
    historical_only = day < datetime.now(india_tz).date()
    total_units = Decimal("0.0000")
    total_cost = Decimal("0.00")
    entries = 0
    partial = False
    balance = Decimal(meter.current_balance)
    blocks = sorted(scenario.blocks, key=lambda row: int(row["start_min"]))
    if not historical_only and balance <= 0:
        meter.power_status = False
        db.query(ActiveAppliance).filter(ActiveAppliance.meter_id == meter.id).delete(synchronize_session=False)
        db.commit()
        return ScenarioApplyItem(
            meter_id=meter.id, room_id=meter.room_id, units_used=Decimal("0.0000"),
            cost=Decimal("0.00"), reading_count=0, partial=True, historical_only=False,
        )
    if not historical_only:
        meter.power_status = True

    for item in blocks:
        start = int(item["start_min"])
        end = int(item["end_min"])
        if end <= start:
            continue
        quantities = item.get("appliance_quantities") or {}
        watts = sum(
            APPLIANCE_BY_ID[appliance_id]["watts"] * int(quantities.get(appliance_id, 1))
            for appliance_id in item["appliance_ids"]
            if appliance_id in APPLIANCE_BY_ID
        )
        requested_units = (Decimal(watts) * Decimal(end - start) / Decimal("60000")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if requested_units <= 0:
            continue
        units = requested_units
        cost = (units * tariff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not historical_only:
            if balance <= 0:
                partial = True
                meter.power_status = False
                break
            if cost > balance:
                units = (balance / tariff).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
                cost = min(balance, (units * tariff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                partial = True
            if units <= 0 or cost <= 0:
                partial = True
                meter.power_status = False
                break

        segments = _hour_segments(start, end)
        allocated_segments = _distribute_block_units(units, cost, segments)
        block_label = str(item.get("label", "Scenario load"))
        for start_minute, segment_units, segment_cost in allocated_segments:
            local_timestamp = datetime.combine(
                day, time(hour=min(start_minute // 60, 23), minute=start_minute % 60), tzinfo=india_tz
            )
            timestamp = local_timestamp.astimezone(timezone.utc)
            if not historical_only:
                balance = max(Decimal("0.00"), (balance - segment_cost).quantize(Decimal("0.01")))
                meter.current_balance = balance
                meter.power_status = balance > 0
            reading = ConsumptionLog(
                meter_id=meter.id, units_used=segment_units, cost=segment_cost,
                balance_after=balance, source="SCENARIO_HOURLY_HISTORY" if historical_only else "SCENARIO_HOURLY",
                note=f"{scenario.name} · {block_label} · {start_minute // 60:02d}:00",
                created_at=timestamp,
            )
            db.add(reading)
            db.flush()
            if not historical_only:
                db.add(WalletLedger(
                    meter_id=meter.id, user_id=None, entry_type="CONSUMPTION", amount=-segment_cost,
                    balance_after=balance, reference_type="READING", reference_id=reading.id,
                ))
            total_units += segment_units
            total_cost += segment_cost
            entries += 1
        if not historical_only and (balance <= 0 or partial):
            if balance <= 0:
                meter.power_status = False
            break

    db.commit()
    db.refresh(meter)
    if partial and not historical_only:
        db.query(ActiveAppliance).filter(ActiveAppliance.meter_id == meter.id).delete(synchronize_session=False)
        db.commit()
    return ScenarioApplyItem(
        meter_id=meter.id, room_id=meter.room_id, units_used=total_units,
        cost=total_cost, reading_count=entries, partial=partial, historical_only=historical_only,
    )


@router.post("/simulation/scenarios/{scenario_id}/apply", response_model=ScenarioApplyRead, tags=["simulation"])
def apply_scenario(
    scenario_id: int,
    payload: ScenarioApplyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScenarioApplyRead:
    scenario = db.get(SimulationScenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.audience == "ADMIN" and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator sign-in is required for this scenario")
    try:
        day = date.fromisoformat(payload.simulation_date) if payload.simulation_date else datetime.now(ZoneInfo("Asia/Kolkata")).date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="simulation_date must use YYYY-MM-DD") from exc
    if day > datetime.now(ZoneInfo("Asia/Kolkata")).date():
        raise HTTPException(status_code=422, detail="Future dates cannot be simulated yet")
    if payload.apply_all:
        if current_user.role != "ADMIN":
            raise HTTPException(status_code=403, detail="Administrator sign-in is required to apply a scenario to all rooms")
        meter_ids = list(db.scalars(select(Meter.id).join(Room).where(Meter.is_active.is_(True), Room.is_active.is_(True)).order_by(Meter.id)).all())
    else:
        if payload.meter_id is None:
            raise HTTPException(status_code=422, detail="Select a meter or enable apply to all rooms")
        meter_ids = [payload.meter_id]
        target = db.get(Meter, payload.meter_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Meter not found")
        _assert_meter_access(target, current_user)
    results = [_apply_scenario_to_meter(db, meter_id, scenario, day) for meter_id in meter_ids]
    return ScenarioApplyRead(scenario_id=scenario.id, simulation_date=day.isoformat(), results=results)
