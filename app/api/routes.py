"""HTTP API endpoints for meters, wallet transactions, usage reports and tickets."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import settings
from app.db.session import get_db
from app.models import ActiveAppliance, ConsumptionLog, Meter, Recharge, Room, SimulationScenario, SupportTicket, User, WalletLedger
from app.schemas import (
    DailyUsage,
    HealthRead,
    MeterRead,
    PowerToggle,
    ReadingCreate,
    ReadingRead,
    RechargeCreate,
    RechargeRead,
    TicketCreate,
    TicketRead,
    UsageReport,
    ActiveApplianceRead, AdminRoomCreate, AdminRoomRead, AdminRoomUpdate, AdminTenantRead, ApplianceRead, ApplianceToggle, AuthAccountRead, LoginCreate, LoginRead, ScenarioApplyCreate, ScenarioApplyItem, ScenarioApplyRead, ScenarioCreate, ScenarioRead, SimulationTickCreate, SimulationTickRead, TenantCreate, TenantUpdate,
)
from app.services.billing import consume_units, recharge_meter, set_power_status
from app.security import get_current_user, get_optional_user, hash_password, issue_access_token, require_admin, verify_password
from app.simulation import APPLIANCES, APPLIANCE_BY_ID

router = APIRouter()


@router.get("/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(app=settings.app_name, environment=settings.environment)


@router.get("/meters", response_model=list[MeterRead], tags=["meters"])
def list_meters(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[Meter]:
    """List available demo meters. Add tenant-scoped authorization before deployment."""
    query = select(Meter).order_by(Meter.id).limit(limit)
    return list(db.scalars(query).all())


@router.get("/meters/{meter_id}", response_model=MeterRead, tags=["meters"])
def get_meter(meter_id: int, db: Session = Depends(get_db)) -> Meter:
    meter = db.get(Meter, meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


@router.patch("/meters/{meter_id}/power", response_model=MeterRead, tags=["meters"])
def toggle_meter_power(
    meter_id: int, payload: PowerToggle, db: Session = Depends(get_db)
) -> Meter:
    return set_power_status(db, meter_id, payload.power_status)


@router.post(
    "/meters/{meter_id}/recharges",
    response_model=RechargeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["wallet"],
)
def create_recharge(
    meter_id: int, payload: RechargeCreate, db: Session = Depends(get_db)
) -> Recharge:
    return recharge_meter(db, meter_id, payload.user_id, payload.amount, payload.idempotency_key)


@router.get("/meters/{meter_id}/recharges", response_model=list[RechargeRead], tags=["wallet"])
def list_recharges(
    meter_id: int,
    status_filter: Literal["SUCCESSFUL", "FAILED"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Recharge]:
    if db.get(Meter, meter_id) is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    query = select(Recharge).where(Recharge.meter_id == meter_id).order_by(Recharge.created_at.desc())
    if status_filter:
        query = query.where(Recharge.status == status_filter)
    return list(db.scalars(query.limit(limit)).all())


@router.post(
    "/meters/{meter_id}/readings",
    response_model=ReadingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["simulation"],
)
def create_simulated_reading(
    meter_id: int, payload: ReadingCreate, db: Session = Depends(get_db)
) -> ConsumptionLog:
    """Record simulated use; protect this write route with admin auth before deployment."""
    reading = consume_units(db, meter_id, payload.units_used)
    if reading is None:
        raise HTTPException(status_code=409, detail="Meter is off or has no available balance")
    return reading


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingRead], tags=["usage"])
def list_readings(
    meter_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ConsumptionLog]:
    if db.get(Meter, meter_id) is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    query = (
        select(ConsumptionLog)
        .where(ConsumptionLog.meter_id == meter_id)
        .order_by(ConsumptionLog.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query).all())


@router.get("/meters/{meter_id}/report", response_model=UsageReport, tags=["analytics"])
def consumption_report(
    meter_id: int,
    period: Literal["1d", "7d", "30d"] = "7d",
    db: Session = Depends(get_db),
) -> UsageReport:
    if db.get(Meter, meter_id) is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    now = datetime.now(timezone.utc)
    if period == "1d":
        # "Today" is the current UTC calendar day; document this until a tenant-local
        # timezone policy is agreed and configured.
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        since = now - timedelta(days={"7d": 7, "30d": 30}[period])
    base_filter = (ConsumptionLog.meter_id == meter_id, ConsumptionLog.created_at >= since)
    aggregate = db.execute(
        select(
            func.coalesce(func.sum(ConsumptionLog.units_used), 0),
            func.coalesce(func.sum(ConsumptionLog.cost), 0),
            func.count(ConsumptionLog.id),
        ).where(*base_filter)
    ).one()
    # func.date is supported by both PostgreSQL and SQLite for the date bucket.
    daily_rows = db.execute(
        select(
            func.date(ConsumptionLog.created_at).label("usage_date"),
            func.coalesce(func.sum(ConsumptionLog.units_used), 0).label("units"),
            func.coalesce(func.sum(ConsumptionLog.cost), 0).label("cost"),
        )
        .where(*base_filter)
        .group_by(func.date(ConsumptionLog.created_at))
        .order_by(func.date(ConsumptionLog.created_at))
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
    )


@router.post("/tickets", response_model=TicketRead, status_code=201, tags=["support"])
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> SupportTicket:
    if db.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    ticket = SupportTicket(
        user_id=payload.user_id,
        issue_type=payload.issue_type.strip(),
        description=payload.description.strip(),
        status="OPEN",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/users/{user_id}/tickets", response_model=list[TicketRead], tags=["support"])
def list_user_tickets(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[SupportTicket]:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    query = (
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query).all())


# ---------------------------------------------------------------------------
# Authentication and admin management. Existing demo meter APIs remain backward
# compatible; new administrative writes are always protected by a signed token.
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=LoginRead, tags=["authentication"])
def login(payload: LoginCreate, db: Session = Depends(get_db)) -> LoginRead:
    user = db.scalar(select(User).where(func.lower(User.username) == payload.username.strip().lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        # Keep the error generic to avoid exposing whether a username exists.
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    if not user.username:
        raise HTTPException(status_code=401, detail="This account is not configured for sign-in")
    return LoginRead(
        access_token=issue_access_token(user),
        account=AuthAccountRead(id=user.id, name=user.name, username=user.username, role=user.role, room_id=user.room_id),
    )


@router.get("/auth/me", response_model=AuthAccountRead, tags=["authentication"])
def who_am_i(user: User = Depends(get_current_user)) -> AuthAccountRead:
    return AuthAccountRead(id=user.id, name=user.name, username=user.username or "", role=user.role, room_id=user.room_id)


def _assert_meter_access(meter: Meter, current_user: User) -> None:
    """Residents may operate only the meter belonging to their assigned room."""
    if current_user.role != "ADMIN" and meter.room_id != current_user.room_id:
        raise HTTPException(status_code=403, detail="Residents can access only their own room's meter")


def _admin_room_read(room: Room) -> AdminRoomRead:
    tenants = [
        AdminTenantRead(id=user.id, name=user.name, username=user.username, phone=user.phone, room_id=user.room_id, role=user.role)
        for user in room.users
    ]
    return AdminRoomRead(id=room.id, room_no=room.room_no, created_at=room.created_at, meter=room.meter, tenants=tenants)


@router.get("/admin/rooms", response_model=list[AdminRoomRead], tags=["administration"])
def admin_list_rooms(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[AdminRoomRead]:
    rooms = list(db.scalars(select(Room).order_by(Room.room_no)).all())
    return [_admin_room_read(room) for room in rooms]


@router.post("/admin/rooms", response_model=AdminRoomRead, status_code=201, tags=["administration"])
def admin_create_room(
    payload: AdminRoomCreate,
    _: User = Depends(require_admin),
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
        reference_type="ROOM_CREATE", reference_id=room.id,
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
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

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
def admin_delete_room(
    room_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    meter = db.scalar(select(Meter).where(Meter.room_id == room_id))
    if meter is not None:
        # Explicit child deletes keep this operation portable across SQLite and
        # PostgreSQL and avoid ORM attempts to null non-nullable meter foreign keys.
        db.execute(delete(ActiveAppliance).where(ActiveAppliance.meter_id == meter.id))
        db.execute(delete(ConsumptionLog).where(ConsumptionLog.meter_id == meter.id))
        db.execute(delete(Recharge).where(Recharge.meter_id == meter.id))
        db.execute(delete(WalletLedger).where(WalletLedger.meter_id == meter.id))
        db.execute(delete(Meter).where(Meter.id == meter.id))

    # Preserve user IDs for unrelated audit records, but revoke tenant sign-in
    # and free unique usernames/phone numbers when their room is removed.
    assigned_users = list(db.scalars(select(User).where(User.room_id == room_id)).all())
    for assigned_user in assigned_users:
        assigned_user.room_id = None
        if assigned_user.role == "RESIDENT":
            assigned_user.username = None
            assigned_user.password_hash = None
            assigned_user.phone = None
    db.execute(delete(Room).where(Room.id == room_id))
    db.commit()
    return {"message": "Room deleted; its meter history was removed and resident logins were disabled."}


@router.post("/admin/rooms/{room_id}/tenants", response_model=AdminTenantRead, status_code=201, tags=["administration"])
def admin_add_tenant(
    room_id: int,
    payload: TenantCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminTenantRead:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
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
    return AdminTenantRead(id=tenant.id, name=tenant.name, username=tenant.username, phone=tenant.phone, room_id=tenant.room_id, role=tenant.role)


@router.get("/simulation/appliances", response_model=list[ApplianceRead], tags=["simulation"])
def list_appliances() -> list[dict]:
    return APPLIANCES


@router.patch("/admin/tenants/{tenant_id}", response_model=AdminTenantRead, tags=["administration"])
def admin_update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminTenantRead:
    tenant = db.get(User, tenant_id)
    if tenant is None or tenant.role != "RESIDENT" or tenant.room_id is None or not tenant.username:
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

    db.commit()
    db.refresh(tenant)
    return AdminTenantRead(
        id=tenant.id, name=tenant.name, username=tenant.username, phone=tenant.phone,
        room_id=tenant.room_id, role=tenant.role,
    )


@router.delete("/admin/tenants/{tenant_id}", tags=["administration"])
def admin_delete_tenant(
    tenant_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    tenant = db.get(User, tenant_id)
    if tenant is None or tenant.role != "RESIDENT" or tenant.room_id is None or not tenant.username:
        raise HTTPException(status_code=404, detail="Active tenant not found")

    # Keep the underlying user row so billing records and support tickets retain
    # their foreign-key identity. Removing the tenant revokes login and unassigns
    # the room; the name remains available for historical records.
    tenant.room_id = None
    tenant.username = None
    tenant.password_hash = None
    tenant.phone = None
    db.commit()
    return {"message": "Tenant removed from the room; sign-in disabled and historical records preserved."}


@router.get("/simulation/scenarios", response_model=list[ScenarioRead], tags=["simulation"])
def list_scenarios(
    audience: Literal["ADMIN", "RESIDENT"] = "RESIDENT",
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[SimulationScenario]:
    query = select(SimulationScenario).where(SimulationScenario.audience == audience)
    if audience == "ADMIN" and (current_user is None or current_user.role != "ADMIN"):
        raise HTTPException(status_code=403, detail="Administrator sign-in is required for admin templates")
    if current_user:
        query = query.where((SimulationScenario.is_builtin.is_(True)) | (SimulationScenario.owner_user_id == current_user.id))
    else:
        query = query.where(SimulationScenario.is_builtin.is_(True))
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
            db.add(ActiveAppliance(meter_id=meter_id, appliance_id=appliance_id, appliance_name=appliance["name"], watts=appliance["watts"]))
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
    live_watts = sum(item.watts for item in loads)
    reading = None
    if live_watts > 0 and meter.power_status and meter.current_balance > 0:
        # Preserve sub-milli-kWh fractions between ticks so low-watt appliances
        # still bill accurately in real-time mode instead of disappearing in rounding.
        total_pending = Decimal("0")
        for load in loads:
            load.pending_kwh = Decimal(load.pending_kwh) + (
                Decimal(load.watts) * payload.elapsed_seconds / Decimal("3600000")
            )
            total_pending += Decimal(load.pending_kwh)
        if total_pending >= Decimal("0.001"):
            units = total_pending.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            names = ", ".join(item.appliance_name for item in loads)
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


def _apply_scenario_to_meter(db: Session, meter_id: int, scenario: SimulationScenario, day: date) -> ScenarioApplyItem:
    meter = db.scalar(select(Meter).where(Meter.id == meter_id).with_for_update())
    if meter is None:
        raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")
    tariff = Decimal(meter.tariff_per_kwh)
    historical_only = day < datetime.now(timezone.utc).date()
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
        watts = sum(APPLIANCE_BY_ID[appliance_id]["watts"] for appliance_id in item["appliance_ids"] if appliance_id in APPLIANCE_BY_ID)
        requested_units = (Decimal(watts) * Decimal(end - start) / Decimal("60000")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if requested_units <= 0:
            continue
        units = requested_units
        cost = (units * tariff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance_after = balance
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
            balance = max(Decimal("0.00"), (balance - cost).quantize(Decimal("0.01")))
            meter.current_balance = balance
            meter.power_status = balance > 0
            balance_after = balance
        timestamp = datetime.combine(day, time(hour=min(start // 60, 23), minute=start % 60), tzinfo=timezone.utc)
        reading = ConsumptionLog(
            meter_id=meter.id, units_used=units, cost=cost, balance_after=balance_after,
            source="SCENARIO_HISTORY" if historical_only else "SCENARIO",
            note=f"{scenario.name} · {item['label']}", created_at=timestamp,
        )
        db.add(reading)
        db.flush()
        if not historical_only:
            db.add(WalletLedger(
                meter_id=meter.id, user_id=None, entry_type="CONSUMPTION", amount=-cost,
                balance_after=balance_after, reference_type="READING", reference_id=reading.id,
            ))
        total_units += units
        total_cost += cost
        entries += 1
        if not meter.power_status and not historical_only:
            partial = True
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
        day = date.fromisoformat(payload.simulation_date) if payload.simulation_date else datetime.now(timezone.utc).date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="simulation_date must use YYYY-MM-DD") from exc
    if day > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Future dates cannot be simulated yet")
    if payload.apply_all:
        if current_user.role != "ADMIN":
            raise HTTPException(status_code=403, detail="Administrator sign-in is required to apply a scenario to all rooms")
        meter_ids = list(db.scalars(select(Meter.id).order_by(Meter.id)).all())
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
