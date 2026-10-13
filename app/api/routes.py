"""HTTP API endpoints for meters, wallet transactions, usage reports and tickets."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import settings
from app.db.session import get_db
from app.models import ConsumptionLog, Meter, Recharge, SupportTicket, User
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
)
from app.services.billing import consume_units, recharge_meter, set_power_status

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
