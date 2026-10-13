"""Create idempotent demo data for local evaluation."""

from decimal import Decimal

from sqlalchemy import select

from app.core import settings
from app.db.session import SessionLocal
from app.models import Meter, Room, User, WalletLedger


def seed() -> None:
    with SessionLocal() as db:
        room = db.scalar(select(Room).where(Room.room_no == "101"))
        if room:
            print("SmartVolt demo data already exists (room 101). Nothing to do.")
            return
        room = Room(room_no="101")
        db.add(room)
        db.flush()
        krunal = User(name="Krunal", room_id=room.id)
        ishan = User(name="Ishan", room_id=room.id)
        db.add_all([krunal, ishan])
        db.flush()
        meter = Meter(
            room_id=room.id,
            current_balance=Decimal("250.00"),
            power_status=True,
            tariff_per_kwh=Decimal(str(settings.default_tariff_per_kwh)).quantize(Decimal("0.0001")),
        )
        db.add(meter)
        db.flush()
        db.add(
            WalletLedger(
                meter_id=meter.id,
                user_id=None,
                entry_type="OPENING_BALANCE",
                amount=Decimal("250.00"),
                balance_after=Decimal("250.00"),
                reference_type="SEED",
                reference_id=None,
            )
        )
        db.commit()
        print(
            f"Seeded SmartVolt demo data: room_id={room.id}, meter_id={meter.id}, "
            f"krunal_user_id={krunal.id}, ishan_user_id={ishan.id}, balance=250.00"
        )


if __name__ == "__main__":
    seed()
