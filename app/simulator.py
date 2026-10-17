"""Standalone synthetic telemetry worker. Run with ``python -m app.simulator``."""

import logging
import random
import signal
import threading
from decimal import Decimal

from sqlalchemy import select

from app.core import settings
from app.db.session import SessionLocal
from app.models import Meter, Room
from app.services.billing import consume_units

logger = logging.getLogger("smartvolt.simulator")


def run_once() -> tuple[int, int]:
    """Run one simulation tick for active room meters; return (readings, skipped)."""
    interval_load_low = max(0.001, settings.simulator_min_kwh)
    interval_load_high = max(interval_load_low, settings.simulator_max_kwh)
    with SessionLocal() as db:
        meter_ids = list(db.scalars(
            select(Meter.id)
            .join(Room, Meter.room_id == Room.id)
            .where(Meter.is_active.is_(True), Room.is_active.is_(True))
            .order_by(Meter.id)
        ).all())

    readings_created = 0
    skipped = 0
    for meter_id in meter_ids:
        try:
            units = Decimal(str(round(random.uniform(interval_load_low, interval_load_high), 4)))
            with SessionLocal() as db:
                reading = consume_units(db, meter_id, units, source="WORKER", note="Autonomous simulator tick")
                if reading is None:
                    skipped += 1
                    logger.info("simulation_tick_skipped meter_id=%s reason=power_off_or_no_balance", meter_id)
                    continue
                readings_created += 1
                logger.info(
                    "simulation_reading_created meter_id=%s units_kwh=%s cost=%s balance_after=%s",
                    meter_id, reading.units_used, reading.cost, reading.balance_after,
                )
        except Exception:
            skipped += 1
            logger.exception("simulation_tick_failed meter_id=%s", meter_id)
    logger.info(
        "simulation_cycle_finished active_meters=%s readings_created=%s skipped=%s",
        len(meter_ids), readings_created, skipped,
    )
    return readings_created, skipped


def run_forever(stop_event: threading.Event | None = None) -> None:
    """Run until SIGINT/SIGTERM or a supplied stop event is set."""
    if not settings.simulator_enabled:
        logger.warning("simulator_disabled set SIMULATOR_ENABLED=true to run the autonomous worker")
        return
    event = stop_event or threading.Event()
    interval = max(1, settings.simulator_interval_seconds)
    logger.info(
        "simulator_started interval_seconds=%s min_kwh=%s max_kwh=%s timezone=UTC-storage/Asia-Kolkata-reports",
        interval, settings.simulator_min_kwh, settings.simulator_max_kwh,
    )
    while not event.is_set():
        run_once()
        # Event.wait permits graceful shutdown during a long configured interval.
        event.wait(interval)
    logger.info("simulator_stopped graceful=true")


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("shutdown_requested signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run_forever(stop_event)


if __name__ == "__main__":
    main()
