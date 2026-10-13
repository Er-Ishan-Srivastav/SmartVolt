"""Standalone stochastic telemetry worker; run with `python -m app.simulator`."""

import random
import time
from decimal import Decimal

from sqlalchemy import select

from app.core import settings
from app.db.session import SessionLocal
from app.models import Meter
from app.services.billing import consume_units


def run_forever() -> None:
    interval = max(1, settings.simulator_interval_seconds)
    low = max(0.001, settings.simulator_min_kwh)
    high = max(low, settings.simulator_max_kwh)
    print(f"SmartVolt simulator started (interval={interval}s, load={low}-{high} kWh per tick)")
    while True:
        with SessionLocal() as db:
            meter_ids = list(db.scalars(select(Meter.id)).all())
        for meter_id in meter_ids:
            try:
                with SessionLocal() as db:
                    reading = consume_units(db, meter_id, Decimal(str(round(random.uniform(low, high), 4))))
                    if reading:
                        print(f"meter={meter_id} used={reading.units_used} kWh cost={reading.cost}")
            except Exception as exc:  # keep the worker alive if one meter fails
                print(f"meter={meter_id} simulation error: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
