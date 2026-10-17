from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_models
from app.db.session import get_db
from app.main import app
from app.models import Meter, Room, User, WalletLedger


@pytest.fixture()
def test_session_factory() -> sessionmaker[Session]:
    load_models()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(test_session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def demo_ids(test_session_factory: sessionmaker[Session]) -> dict[str, int]:
    with test_session_factory() as db:
        room = Room(room_no="101")
        db.add(room)
        db.flush()
        from app.security import hash_password
        user = User(name="Ishan", username="ishan", password_hash=hash_password("resident123"), role="RESIDENT", room_id=room.id)
        other_room = Room(room_no="202")
        db.add(other_room)
        db.flush()
        outside_user = User(name="Other tenant", username="otherresident", password_hash=hash_password("resident123"), role="RESIDENT", room_id=other_room.id)
        db.add_all([user, outside_user])
        db.flush()
        meter = Meter(
            room_id=room.id,
            current_balance=Decimal("10.00"),
            power_status=True,
            tariff_per_kwh=Decimal("8.0000"),
        )
        db.add(meter)
        db.flush()
        db.add(
            WalletLedger(
                meter_id=meter.id,
                user_id=None,
                entry_type="OPENING_BALANCE",
                amount=Decimal("10.00"),
                balance_after=Decimal("10.00"),
                reference_type="TEST",
            )
        )
        db.commit()
        return {
            "room_id": room.id,
            "user_id": user.id,
            "outside_user_id": outside_user.id,
            "meter_id": meter.id,
        }


@pytest.fixture()
def resident_headers(client: TestClient, demo_ids: dict[str, int]) -> dict[str, str]:
    """Authenticate the ordinary data tests as the seeded resident."""
    response = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    client.headers.update(headers)
    return headers
