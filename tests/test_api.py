from decimal import Decimal

from sqlalchemy import select

from app.models import Meter, Recharge, WalletLedger


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_recharge_updates_balance_and_ledger(client, test_session_factory, demo_ids):
    response = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/recharges",
        json={"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "payment-demo-1"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["amount"] == "25.00"

    with test_session_factory() as db:
        meter = db.get(Meter, demo_ids["meter_id"])
        assert meter.current_balance == Decimal("35.00")
        entries = list(db.scalars(select(WalletLedger).where(WalletLedger.entry_type == "RECHARGE")))
        assert len(entries) == 1
        assert entries[0].amount == Decimal("25.00")


def test_recharge_idempotency_does_not_double_credit(client, test_session_factory, demo_ids):
    payload = {"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "retry-1"}
    first = client.post(f"/api/v1/meters/{demo_ids['meter_id']}/recharges", json=payload)
    second = client.post(f"/api/v1/meters/{demo_ids['meter_id']}/recharges", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("35.00")
        assert len(list(db.scalars(select(Recharge)))) == 1


def test_recharge_rejects_user_from_another_room(client, test_session_factory, demo_ids):
    response = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/recharges",
        json={"user_id": demo_ids["outside_user_id"], "amount": "20.00"},
    )
    assert response.status_code == 403
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("10.00")


def test_consumption_caps_debit_and_turns_power_off(client, test_session_factory, demo_ids):
    response = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/readings",
        json={"units_used": "5.0000"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["cost"] == "10.00"
    assert response.json()["balance_after"] == "0.00"

    with test_session_factory() as db:
        meter = db.get(Meter, demo_ids["meter_id"])
        assert meter.current_balance == Decimal("0.00")
        assert meter.power_status is False
        ledger = list(db.scalars(select(WalletLedger).where(WalletLedger.entry_type == "CONSUMPTION")))
        assert len(ledger) == 1
        assert ledger[0].amount == Decimal("-10.00")


def test_power_cannot_turn_on_with_zero_balance(client, test_session_factory, demo_ids):
    with test_session_factory() as db:
        meter = db.get(Meter, demo_ids["meter_id"])
        meter.current_balance = Decimal("0.00")
        meter.power_status = False
        db.commit()
    response = client.patch(
        f"/api/v1/meters/{demo_ids['meter_id']}/power", json={"power_status": True}
    )
    assert response.status_code == 409


def test_usage_report_aggregates_readings(client, demo_ids):
    created = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/readings", json={"units_used": "0.5000"}
    )
    assert created.status_code == 201, created.text
    response = client.get(f"/api/v1/meters/{demo_ids['meter_id']}/report?period=7d")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reading_count"] == 1
    assert body["total_units"] == "0.5000"
    assert body["total_cost"] == "4.00"


def test_idempotency_key_cannot_be_reused_for_different_amount(client, test_session_factory, demo_ids):
    path = f"/api/v1/meters/{demo_ids['meter_id']}/recharges"
    first = client.post(path, json={"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "same-key"})
    conflict = client.post(path, json={"user_id": demo_ids["user_id"], "amount": "45.00", "idempotency_key": "same-key"})
    assert first.status_code == 201
    assert conflict.status_code == 409
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("35.00")
        assert len(list(db.scalars(select(Recharge)))) == 1


def test_list_meters_includes_demo_meter(client, demo_ids):
    response = client.get("/api/v1/meters")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [demo_ids["meter_id"]]


def test_support_ticket_can_be_created_and_listed(client, demo_ids):
    created = client.post(
        "/api/v1/tickets",
        json={"user_id": demo_ids["user_id"], "issue_type": "BILLING", "description": "Please verify the last recharge."},
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]
    listed = client.get(f"/api/v1/users/{demo_ids['user_id']}/tickets")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == ticket_id
    assert listed.json()[0]["status"] == "OPEN"


def test_admin_login_required_for_room_management(client, test_session_factory):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        db.add(User(name="Demo Admin", username="admin", password_hash=hash_password("Admin123!"), role="ADMIN"))
        db.commit()

    denied = client.post("/api/v1/admin/rooms", json={"room_no": "303"})
    assert denied.status_code == 401

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin123!"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["account"]["role"] == "ADMIN"
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    created = client.post(
        "/api/v1/admin/rooms",
        headers=headers,
        json={
            "room_no": "303", "tariff_per_kwh": "9.5", "opening_balance": "300",
            "first_tenant_name": "New Tenant", "first_tenant_username": "newtenant",
            "first_tenant_password": "tenant-pass-123", "first_tenant_phone": "99900000999",
        },
    )
    assert created.status_code == 201, created.text
    result = created.json()
    assert result["room_no"] == "303"
    assert Decimal(result["meter"]["current_balance"]) == Decimal("300.00")
    assert result["tenants"][0]["username"] == "newtenant"


def test_resident_cannot_create_room(client, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        resident = db.get(User, demo_ids["user_id"])
        resident.username = "ishan"
        resident.password_hash = hash_password("resident123")
        resident.role = "RESIDENT"
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    assert login.status_code == 200
    response = client.post(
        "/api/v1/admin/rooms",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"room_no": "404"},
    )
    assert response.status_code == 403


def test_appliance_ticks_bill_live_load_and_turn_off_at_zero(client, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        resident = db.get(User, demo_ids["user_id"])
        resident.username = "ishan"
        resident.password_hash = hash_password("resident123")
        resident.role = "RESIDENT"
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    meter_id = demo_ids["meter_id"]
    denied = client.put(f"/api/v1/meters/{meter_id}/simulation/appliances/router", json={"enabled": True})
    assert denied.status_code == 401
    enabled = client.put(f"/api/v1/meters/{meter_id}/simulation/appliances/router", headers=headers, json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    # 12 W for 5 simulated minutes = 0.001 kWh, enough to survive four-decimal rounding.
    tick = client.post(f"/api/v1/meters/{meter_id}/simulation/tick", headers=headers, json={"elapsed_seconds": 300})
    assert tick.status_code == 200, tick.text
    assert tick.json()["live_watts"] == 12
    assert tick.json()["reading"] is not None
    assert tick.json()["reading"]["source"] == "LIVE"
    with test_session_factory() as db:
        meter = db.get(Meter, meter_id)
        assert meter.current_balance < Decimal("10.00")


def test_scenario_replay_today_debits_wallet_and_past_day_does_not(client, test_session_factory, demo_ids):
    from datetime import datetime, timedelta, timezone
    from app.models import SimulationScenario, User
    from app.security import hash_password

    with test_session_factory() as db:
        resident = db.get(User, demo_ids["user_id"])
        resident.username = "ishan"
        resident.password_hash = hash_password("resident123")
        resident.role = "RESIDENT"
        scenario = SimulationScenario(
            slug="test-mini-scenario", name="Test mini scenario", audience="RESIDENT",
            description="Test", is_builtin=True,
            blocks=[{"label": "Fan for one hour", "start_min": 0, "end_min": 60, "appliance_ids": ["fan"]}],
        )
        db.add(scenario); db.commit(); db.refresh(scenario)
        scenario_id = scenario.id
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    meter_id = demo_ids["meter_id"]
    today = datetime.now(timezone.utc).date().isoformat()
    assert client.post(f"/api/v1/simulation/scenarios/{scenario_id}/apply", json={"meter_id": meter_id, "simulation_date": today}).status_code == 401
    applied = client.post(f"/api/v1/simulation/scenarios/{scenario_id}/apply", headers=headers, json={"meter_id": meter_id, "simulation_date": today})
    assert applied.status_code == 200, applied.text
    assert float(applied.json()["results"][0]["units_used"]) > 0
    with test_session_factory() as db:
        balance_after_today = db.get(Meter, meter_id).current_balance
    past = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    history = client.post(f"/api/v1/simulation/scenarios/{scenario_id}/apply", headers=headers, json={"meter_id": meter_id, "simulation_date": past})
    assert history.status_code == 200, history.text
    assert history.json()["results"][0]["historical_only"] is True
    with test_session_factory() as db:
        assert db.get(Meter, meter_id).current_balance == balance_after_today


def test_custom_scenario_requires_valid_login_and_filters_appliances(client, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        user = db.get(User, demo_ids["user_id"])
        user.username = "ishan"
        user.password_hash = hash_password("resident123")
        user.role = "RESIDENT"
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post("/api/v1/simulation/scenarios", headers=headers, json={
        "name": "My custom evening", "audience": "RESIDENT", "description": "Test template", "blocks": [
            {"label": "Evening fan", "start_min": 1080, "end_min": 1200, "appliance_ids": ["fan"]}
        ]
    })
    assert created.status_code == 201, created.text
    bad = client.post("/api/v1/simulation/scenarios", headers=headers, json={
        "name": "Bad unknown load", "audience": "RESIDENT", "blocks": [
            {"label": "Mystery load", "start_min": 0, "end_min": 60, "appliance_ids": ["quantum-toaster"]}
        ]
    })
    assert bad.status_code == 422


def test_resident_cannot_operate_another_rooms_load(client, test_session_factory, demo_ids):
    from app.models import User, Meter
    from app.security import hash_password

    with test_session_factory() as db:
        resident = db.get(User, demo_ids["user_id"])
        resident.username = "ishan"
        resident.password_hash = hash_password("resident123")
        resident.role = "RESIDENT"
        other_meter = Meter(room_id=db.get(User, demo_ids["outside_user_id"]).room_id, current_balance=Decimal("20.00"), power_status=True, tariff_per_kwh=Decimal("8.00"))
        db.add(other_meter)
        db.commit()
        other_meter_id = other_meter.id
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.put(f"/api/v1/meters/{other_meter_id}/simulation/appliances/fan", headers=headers, json={"enabled": True})
    assert response.status_code == 403


def test_admin_can_apply_scenario_to_all_rooms_when_one_meter_is_empty(client, test_session_factory, demo_ids):
    from app.models import Room, Meter, User, SimulationScenario
    from app.security import hash_password

    with test_session_factory() as db:
        admin = User(
            name="Load Admin", username="loadadmin",
            password_hash=hash_password("admin-pass-123"), role="ADMIN",
        )
        empty_room = Room(room_no="707")
        db.add_all([admin, empty_room])
        db.flush()
        empty_meter = Meter(
            room_id=empty_room.id, current_balance=Decimal("0.00"),
            power_status=False, tariff_per_kwh=Decimal("8.00"),
        )
        scenario = SimulationScenario(
            slug="admin-all-rooms-test", name="Hostel test day", audience="ADMIN",
            description="Small admin scenario", is_builtin=True,
            blocks=[{"label": "Fan for an hour", "start_min": 0, "end_min": 60, "appliance_ids": ["fan"]}],
        )
        db.add_all([empty_meter, scenario])
        db.commit()
        scenario_id = scenario.id
        empty_meter_id = empty_meter.id

    login = client.post("/api/v1/auth/login", json={"username": "loadadmin", "password": "admin-pass-123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    applied = client.post(
        f"/api/v1/simulation/scenarios/{scenario_id}/apply",
        headers=headers,
        json={"apply_all": True},
    )
    assert applied.status_code == 200, applied.text
    results = applied.json()["results"]
    assert len(results) == 2
    empty_result = next(item for item in results if item["meter_id"] == empty_meter_id)
    assert empty_result["partial"] is True
    assert empty_result["reading_count"] == 0
    assert any(Decimal(item["units_used"]) > 0 for item in results if item["meter_id"] != empty_meter_id)
