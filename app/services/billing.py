"""Transactional wallet, relay and simulated consumption operations."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ConsumptionLog, Meter, Recharge, User, WalletLedger

MONEY = Decimal("0.01")
UNITS = Decimal("0.0001")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _units(value: Decimal) -> Decimal:
    return value.quantize(UNITS, rounding=ROUND_HALF_UP)


def _locked_meter(db: Session, meter_id: int) -> Meter:
    """Lock meter row for update on PostgreSQL; SQLite ignores FOR UPDATE."""
    meter = db.scalar(select(Meter).where(Meter.id == meter_id).with_for_update())
    if meter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter not found")
    return meter


def recharge_meter(
    db: Session,
    meter_id: int,
    user_id: int | None,
    amount: Decimal,
    idempotency_key: str | None = None,
    *,
    actor_user_id: int | None = None,
    allow_empty_target: bool = False,
) -> Recharge:
    """Credit one active meter and append recharge + ledger records atomically.

    ``user_id`` is optional tenant context; ``actor_user_id`` is the account that
    performed the transaction. They are intentionally separate so admin actions
    are never falsely attributed to the resident whose room was selected.
    """
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Recharge amount must be greater than zero")
    amount = _money(amount)

    def matches(existing: Recharge) -> bool:
        return (
            existing.meter_id == meter_id
            and existing.user_id == user_id
            and existing.amount == amount
            and existing.actor_user_id == actor_user_id
        )

    try:
        if idempotency_key:
            existing = db.scalar(select(Recharge).where(Recharge.idempotency_key == idempotency_key))
            if existing:
                if not matches(existing):
                    raise HTTPException(status_code=409, detail="Idempotency key already used for another request")
                return existing

        meter = _locked_meter(db, meter_id)
        if not meter.is_active or not meter.room.is_active:
            raise HTTPException(status_code=404, detail="Active meter not found")

        # Re-check after taking the per-meter lock to avoid double credits on retry.
        if idempotency_key:
            existing = db.scalar(select(Recharge).where(Recharge.idempotency_key == idempotency_key))
            if existing:
                if not matches(existing):
                    raise HTTPException(status_code=409, detail="Idempotency key already used for another request")
                db.rollback()
                return existing

        target_user = db.get(User, user_id) if user_id is not None else None
        if user_id is not None:
            if target_user is None or target_user.role != "RESIDENT" or not target_user.is_active:
                raise HTTPException(status_code=404, detail="Active tenant not found")
            if target_user.room_id != meter.room_id:
                raise HTTPException(status_code=403, detail="Tenant is not assigned to this meter's room")
        elif not allow_empty_target:
            raise HTTPException(status_code=422, detail="A tenant context is required for this recharge")

        actor = db.get(User, actor_user_id) if actor_user_id is not None else None
        if actor_user_id is not None and (actor is None or not actor.is_active):
            raise HTTPException(status_code=401, detail="Transaction actor is not active")
        if actor is not None and actor.role != "ADMIN":
            if target_user is None or actor.id != target_user.id or actor.room_id != meter.room_id:
                raise HTTPException(status_code=403, detail="Residents can recharge only their own room's meter")

        meter.current_balance = _money(meter.current_balance + amount)
        if meter.current_balance > 0:
            meter.power_status = True
        recharge = Recharge(
            meter_id=meter.id,
            user_id=target_user.id if target_user else None,
            actor_user_id=actor.id if actor else None,
            amount=amount,
            status="SUCCESSFUL",
            idempotency_key=idempotency_key,
        )
        db.add(recharge)
        db.flush()
        db.add(
            WalletLedger(
                meter_id=meter.id,
                user_id=target_user.id if target_user else None,
                actor_user_id=actor.id if actor else None,
                entry_type="RECHARGE",
                amount=amount,
                balance_after=meter.current_balance,
                reference_type="RECHARGE",
                reference_id=recharge.id,
            )
        )
        db.commit()
        db.refresh(recharge)
        return recharge
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(Recharge).where(Recharge.idempotency_key == idempotency_key))
            if existing:
                if matches(existing):
                    return existing
                raise HTTPException(status_code=409, detail="Idempotency key already used for another request") from exc
        raise HTTPException(status_code=409, detail="Recharge conflicts with existing data") from exc
    except Exception:
        db.rollback()
        raise


def set_power_status(db: Session, meter_id: int, power_status: bool) -> Meter:
    """Set simulated relay state; prevent powering on an empty prepaid meter."""
    meter = _locked_meter(db, meter_id)
    if power_status and meter.current_balance <= 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cannot turn power on with a zero balance")
    meter.power_status = power_status
    db.commit()
    db.refresh(meter)
    return meter


def consume_units(
    db: Session,
    meter_id: int,
    requested_units: Decimal,
    *,
    source: str = "MANUAL",
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> ConsumptionLog | None:
    """Debit only affordable kWh and switch the relay off when balance is exhausted.

    Returns ``None`` if the meter is off, no units were requested, or no balance remains.
    The meter balance, reading and ledger debit are committed together.
    """
    if requested_units <= 0:
        raise HTTPException(status_code=400, detail="Units used must be greater than zero")
    meter = _locked_meter(db, meter_id)
    if not meter.power_status or meter.current_balance <= 0:
        meter.power_status = False if meter.current_balance <= 0 else meter.power_status
        db.commit()
        return None

    requested_units = _units(requested_units)
    requested_cost = _money(requested_units * meter.tariff_per_kwh)
    if requested_cost <= meter.current_balance:
        actual_units = requested_units
        actual_cost = requested_cost
    else:
        # Debit no more than the wallet contains. Quantize usage to four decimals;
        # cost is rounded to currency precision and is never allowed above balance.
        affordable_units = _units(meter.current_balance / meter.tariff_per_kwh)
        actual_units = min(requested_units, affordable_units)
        actual_cost = min(meter.current_balance, _money(actual_units * meter.tariff_per_kwh))

    if actual_units <= 0 or actual_cost <= 0:
        meter.power_status = False
        db.commit()
        return None

    meter.current_balance = _money(max(Decimal("0.00"), meter.current_balance - actual_cost))
    if meter.current_balance == 0:
        meter.power_status = False

    reading = ConsumptionLog(
        meter_id=meter.id,
        units_used=actual_units,
        cost=actual_cost,
        balance_after=meter.current_balance,
        source=source,
        note=note,
        **({"created_at": occurred_at} if occurred_at is not None else {}),
    )
    db.add(reading)
    db.flush()
    db.add(
        WalletLedger(
            meter_id=meter.id,
            user_id=None,
            entry_type="CONSUMPTION",
            amount=-actual_cost,
            balance_after=meter.current_balance,
            reference_type="READING",
            reference_id=reading.id,
        )
    )
    db.commit()
    db.refresh(reading)
    return reading
