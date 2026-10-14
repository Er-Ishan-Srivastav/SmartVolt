"""Create idempotent demo data for local evaluation."""

from decimal import Decimal

from sqlalchemy import select

from app.core import settings
from app.db.session import SessionLocal
from app.models import Meter, Room, User, WalletLedger


def seed() -> None:
    from datetime import datetime, time, timedelta, timezone

    from sqlalchemy import func

    from app.models import ConsumptionLog, SimulationScenario
    from app.security import hash_password
    from app.simulation import BUILTIN_SCENARIOS

    with SessionLocal() as db:
        room = db.scalar(select(Room).where(Room.room_no == "101"))
        if room is None:
            room = Room(room_no="101")
            db.add(room)
            db.flush()

        people = {person.name.lower(): person for person in db.scalars(select(User).where(User.room_id == room.id)).all()}
        defaults = [("Krunal", "krunal", "99900000101"), ("Ishan", "ishan", "99900000102")]
        for name, username, phone in defaults:
            person = people.get(name.lower())
            if person is None:
                person = User(name=name, room_id=room.id)
                db.add(person)
                db.flush()
            if not person.username:
                person.username = username
            if not person.password_hash:
                person.password_hash = hash_password("resident123")
            if not person.phone:
                # The sample phone values are fake and unique within the demo DB.
                person.phone = phone
            person.role = "RESIDENT"

        admin = db.scalar(select(User).where(func.lower(User.username) == settings.admin_username.lower()))
        if admin is None:
            admin = User(
                name="SmartVolt Administrator", username=settings.admin_username,
                password_hash=hash_password(settings.admin_password), role="ADMIN", room_id=None,
            )
            db.add(admin)
        else:
            admin.role = "ADMIN"
            if not admin.password_hash:
                admin.password_hash = hash_password(settings.admin_password)

        meter = db.scalar(select(Meter).where(Meter.room_id == room.id))
        if meter is None:
            meter = Meter(
                room_id=room.id,
                current_balance=Decimal("250.00"),
                power_status=True,
                tariff_per_kwh=Decimal(str(settings.default_tariff_per_kwh)).quantize(Decimal("0.0001")),
            )
            db.add(meter)
            db.flush()
            db.add(WalletLedger(
                meter_id=meter.id, user_id=None, entry_type="OPENING_BALANCE",
                amount=Decimal("250.00"), balance_after=Decimal("250.00"),
                reference_type="SEED", reference_id=None,
            ))

        db.flush()

        for template in BUILTIN_SCENARIOS:
            existing = db.scalar(select(SimulationScenario).where(SimulationScenario.slug == template["slug"]))
            if existing is None:
                db.add(SimulationScenario(
                    slug=template["slug"], name=template["name"], audience=template["audience"],
                    description=template["description"], blocks=template["blocks"],
                    is_builtin=True, owner_user_id=None,
                ))

        has_seeded_history = db.scalar(
            select(func.count(ConsumptionLog.id)).where(
                ConsumptionLog.meter_id == meter.id,
                ConsumptionLog.source == "HISTORICAL",
                ConsumptionLog.note == "Seeded demo usage history",
            )
        ) or 0
        if has_seeded_history == 0:
            # Seven fixed demo days. These rows are historical telemetry only: the
            # current wallet is not debited again when the seed command is repeated.
            # Existing user-created readings do not suppress this one-time demo backfill.
            daily_units = [Decimal(value) for value in ("2.8000", "3.2000", "4.1000", "2.2000", "3.9000", "5.3000", "3.6000")]
            tariff = Decimal(meter.tariff_per_kwh)
            total_cost = sum((units * tariff).quantize(Decimal("0.01")) for units in daily_units)
            historic_balance = Decimal(meter.current_balance) + total_cost
            today = datetime.now(timezone.utc).date()
            for days_ago, units in reversed(list(enumerate(daily_units, start=1))):
                cost = (units * tariff).quantize(Decimal("0.01"))
                historic_balance -= cost
                day = today - timedelta(days=days_ago)
                db.add(ConsumptionLog(
                    meter_id=meter.id, units_used=units, cost=cost,
                    balance_after=max(Decimal("0.00"), historic_balance),
                    source="HISTORICAL", note="Seeded demo usage history",
                    created_at=datetime.combine(day, time(hour=20), tzinfo=timezone.utc),
                ))

        db.commit()
        krunal = db.scalar(select(User).where(User.username == "krunal"))
        ishan = db.scalar(select(User).where(User.username == "ishan"))
        print(
            f"SmartVolt demo data ready: room_id={room.id}, meter_id={meter.id}, "
            f"admin_username={settings.admin_username}, krunal_user_id={krunal.id if krunal else '-'}, "
            f"ishan_user_id={ishan.id if ishan else '-'}, current_balance={meter.current_balance}"
        )


if __name__ == "__main__":
    seed()
