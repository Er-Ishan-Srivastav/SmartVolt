"""Transactional wallet, relay and simulated consumption operations."""

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
    db: Session, meter_id: int, user_id: int, amount: Decimal, idempotency_key: str | None = None
) -> Recharge:
    """Credit a meter and append recharge + ledger records atomically."""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Recharge amount must be greater than zero")
    try:
        if idempotency_key:
            existing = db.scalar(select(Recharge).where(Recharge.idempotency_key == idempotency_key))
            if existing:
                if existing.meter_id != meter_id or existing.user_id != user_id or existing.amount != amount:
                    raise HTTPException(status_code=409, detail="Idempotency key already used for another request")
                return existing

        meter = _locked_meter(db, meter_id)
        if idempotency_key:
            # Another request for this meter may have committed while this one waited
            # for the row lock, so check again inside the serialized transaction.
            existing = db.scalar(select(Recharge).where(Recharge.idempotency_key == idempotency_key))
            if existing:
                if existing.meter_id != meter_id or existing.user_id != user_id or existing.amount != amount:
                    raise HTTPException(status_code=409, detail="Idempotency key already used for another request")
                db.rollback()
                return existing
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.room_id != meter.room_id:
            raise HTTPException(status_code=403, detail="User is not assigned to this meter's room")

        amount = _money(amount)
        meter.current_balance = _money(meter.current_balance + amount)
        if meter.current_balance > 0:
            meter.power_status = True
        recharge = Recharge(
            meter_id=meter.id,
            user_id=user.id,
            amount=amount,
            status="SUCCESSFUL",
            idempotency_key=idempotency_key,
        )
        db.add(recharge)
        db.flush()
        db.add(
            WalletLedger(
                meter_id=meter.id,
                user_id=user.id,
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
                if existing.meter_id == meter_id and existing.user_id == user_id and existing.amount == amount:
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


def consume_units(db: Session, meter_id: int, requested_units: Decimal) -> ConsumptionLog | None:
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
