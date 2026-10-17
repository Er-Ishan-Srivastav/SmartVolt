from decimal import Decimal

from sqlalchemy import select

from app.models import Meter, Recharge, WalletLedger


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_recharge_updates_balance_and_ledger(client, resident_headers, test_session_factory, demo_ids):
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
        assert entries[0].actor_user_id == demo_ids["user_id"]


def test_recharge_idempotency_does_not_double_credit(client, resident_headers, test_session_factory, demo_ids):
    payload = {"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "retry-1"}
    first = client.post(f"/api/v1/meters/{demo_ids['meter_id']}/recharges", json=payload)
    second = client.post(f"/api/v1/meters/{demo_ids['meter_id']}/recharges", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("35.00")
        assert len(list(db.scalars(select(Recharge)))) == 1


def test_recharge_rejects_user_from_another_room(client, resident_headers, test_session_factory, demo_ids):
    response = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/recharges",
        json={"user_id": demo_ids["outside_user_id"], "amount": "20.00"},
    )
    assert response.status_code == 403
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("10.00")


def test_consumption_caps_debit_and_turns_power_off(client, resident_headers, test_session_factory, demo_ids):
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


def test_power_cannot_turn_on_with_zero_balance(client, resident_headers, test_session_factory, demo_ids):
    with test_session_factory() as db:
        meter = db.get(Meter, demo_ids["meter_id"])
        meter.current_balance = Decimal("0.00")
        meter.power_status = False
        db.commit()
    response = client.patch(
        f"/api/v1/meters/{demo_ids['meter_id']}/power", json={"power_status": True}
    )
    assert response.status_code == 409


def test_usage_report_aggregates_readings(client, resident_headers, demo_ids):
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


def test_idempotency_key_cannot_be_reused_for_different_amount(client, resident_headers, test_session_factory, demo_ids):
    path = f"/api/v1/meters/{demo_ids['meter_id']}/recharges"
    first = client.post(path, json={"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "same-key"})
    conflict = client.post(path, json={"user_id": demo_ids["user_id"], "amount": "45.00", "idempotency_key": "same-key"})
    assert first.status_code == 201
    assert conflict.status_code == 409
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("35.00")
        assert len(list(db.scalars(select(Recharge)))) == 1


def test_list_meters_includes_demo_meter(client, resident_headers, demo_ids):
    response = client.get("/api/v1/meters")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [demo_ids["meter_id"]]


def test_support_ticket_can_be_created_and_listed(client, resident_headers, demo_ids):
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


def test_admin_can_view_resident_support_tickets_but_residents_cannot_view_all(client, resident_headers, test_session_factory, demo_ids):
    created = client.post(
        "/api/v1/tickets",
        headers=resident_headers,
        json={"user_id": demo_ids["user_id"], "issue_type": "METER", "description": "The meter display is not updating."},
    )
    assert created.status_code == 201, created.text

    resident_denied = client.get("/api/v1/admin/tickets", headers=resident_headers)
    assert resident_denied.status_code == 403

    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        db.add(User(name="Support Administrator", username="supportadmin", password_hash=hash_password("admin-test-pass"), role="ADMIN"))
        db.commit()

    login = client.post("/api/v1/auth/login", json={"username": "supportadmin", "password": "admin-test-pass"})
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = client.get("/api/v1/admin/tickets?limit=100", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    ticket = listed.json()[0]
    assert ticket["id"] == created.json()["id"]
    assert ticket["requester_name"] == "Ishan"
    assert ticket["requester_username"] == "ishan"
    assert ticket["room_no"] == "101"
    assert ticket["description"] == "The meter display is not updating."


def test_admin_ticket_list_requires_authentication(client):
    response = client.get("/api/v1/admin/tickets")
    assert response.status_code == 401


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
    assert result["room_code"].startswith("ROM-")
    assert result["is_active"] is True
    assert result["meter"]["meter_code"].startswith("MTR-")
    assert Decimal(result["meter"]["current_balance"]) == Decimal("300.00")
    assert result["tenants"][0]["username"] == "newtenant"
    assert result["tenants"][0]["tenant_code"].startswith("TEN-")


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


def test_live_appliance_quantity_changes_wattage_and_billing(client, test_session_factory, demo_ids):
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

    enabled = client.put(
        f"/api/v1/meters/{meter_id}/simulation/appliances/fan",
        headers=headers,
        json={"enabled": True, "quantity": 3},
    )
    assert enabled.status_code == 200, enabled.text
    fan = next(item for item in enabled.json() if item["appliance_id"] == "fan")
    assert fan["quantity"] == 3
    assert fan["watts"] == 75  # per-unit wattage remains stable in the API

    tick = client.post(
        f"/api/v1/meters/{meter_id}/simulation/tick",
        headers=headers,
        json={"elapsed_seconds": 3600},
    )
    assert tick.status_code == 200, tick.text
    assert tick.json()["live_watts"] == 225
    assert Decimal(tick.json()["reading"]["units_used"]) == Decimal("0.2250")
    assert Decimal(tick.json()["reading"]["cost"]) == Decimal("1.80")

    updated = client.put(
        f"/api/v1/meters/{meter_id}/simulation/appliances/fan",
        headers=headers,
        json={"enabled": True, "quantity": 2},
    )
    assert updated.status_code == 200, updated.text
    assert next(item for item in updated.json() if item["appliance_id"] == "fan")["quantity"] == 2

    invalid = client.put(
        f"/api/v1/meters/{meter_id}/simulation/appliances/fan",
        headers=headers,
        json={"enabled": True, "quantity": 101},
    )
    assert invalid.status_code == 422


def test_scenario_replay_today_debits_wallet_and_past_day_does_not(client, test_session_factory, demo_ids):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
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
            blocks=[{"label": "Two fans for one hour", "start_min": 0, "end_min": 60, "appliance_ids": ["fan"], "appliance_quantities": {"fan": 2}}],
        )
        db.add(scenario); db.commit(); db.refresh(scenario)
        scenario_id = scenario.id
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    meter_id = demo_ids["meter_id"]
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    assert client.post(f"/api/v1/simulation/scenarios/{scenario_id}/apply", json={"meter_id": meter_id, "simulation_date": today}).status_code == 401
    applied = client.post(f"/api/v1/simulation/scenarios/{scenario_id}/apply", headers=headers, json={"meter_id": meter_id, "simulation_date": today})
    assert applied.status_code == 200, applied.text
    assert Decimal(applied.json()["results"][0]["units_used"]) == Decimal("0.1500")
    assert Decimal(applied.json()["results"][0]["cost"]) == Decimal("1.20")
    with test_session_factory() as db:
        balance_after_today = db.get(Meter, meter_id).current_balance
    past = (datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=2)).isoformat()
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
            {"label": "Evening fan", "start_min": 1080, "end_min": 1200, "appliance_ids": ["fan"], "appliance_quantities": {"fan": 3}}
        ]
    })
    assert created.status_code == 201, created.text
    assert created.json()["blocks"][0]["appliance_quantities"]["fan"] == 3
    bad = client.post("/api/v1/simulation/scenarios", headers=headers, json={
        "name": "Bad unknown load", "audience": "RESIDENT", "blocks": [
            {"label": "Mystery load", "start_min": 0, "end_min": 60, "appliance_ids": ["quantum-toaster"]}
        ]
    })
    assert bad.status_code == 422

    invalid_quantity = client.post("/api/v1/simulation/scenarios", headers=headers, json={
        "name": "Too many fans", "audience": "RESIDENT", "blocks": [
            {"label": "Evening fan", "start_min": 1080, "end_min": 1200, "appliance_ids": ["fan"], "appliance_quantities": {"fan": 101}}
        ]
    })
    assert invalid_quantity.status_code == 422

    unrelated_quantity = client.post("/api/v1/simulation/scenarios", headers=headers, json={
        "name": "Unrelated quantity", "audience": "RESIDENT", "blocks": [
            {"label": "Evening fan", "start_min": 1080, "end_min": 1200, "appliance_ids": ["fan"], "appliance_quantities": {"router": 2}}
        ]
    })
    assert unrelated_quantity.status_code == 422


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


def _admin_headers(client, test_session_factory, username="manageadmin"):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(name="Admin", username=username, password_hash=hash_password("admin-pass-123"), role="ADMIN"))
            db.commit()
    login = client.post("/api/v1/auth/login", json={"username": username, "password": "admin-pass-123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_admin_can_edit_room_and_updates_meter_tariff(client, test_session_factory, demo_ids):
    headers = _admin_headers(client, test_session_factory)

    updated = client.patch(
        f"/api/v1/admin/rooms/{demo_ids['room_id']}",
        headers=headers,
        json={"room_no": "101A", "tariff_per_kwh": "9.2500"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["room_no"] == "101A"
    assert updated.json()["meter"]["tariff_per_kwh"] == "9.2500"

    duplicate = client.patch(
        f"/api/v1/admin/rooms/{demo_ids['room_id']}",
        headers=headers,
        json={"room_no": "202", "tariff_per_kwh": "9.2500"},
    )
    assert duplicate.status_code == 409

    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).tariff_per_kwh == Decimal("9.2500")


def test_admin_can_edit_and_remove_tenant_without_losing_history(client, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    headers = _admin_headers(client, test_session_factory)
    with test_session_factory() as db:
        tenant = db.get(User, demo_ids["user_id"])
        tenant.name = "Original Tenant"
        tenant.username = "originaltenant"
        tenant.phone = "9991110000"
        tenant.password_hash = hash_password("tenant-pass-123")
        tenant.role = "RESIDENT"
        db.commit()
        tenant_id = tenant.id

    updated = client.patch(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers=headers,
        json={"name": "Updated Tenant", "username": "updatedtenant", "phone": "9991110001", "password": "new-pass-123"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated Tenant"
    assert updated.json()["username"] == "updatedtenant"
    assert updated.json()["phone"] == "9991110001"

    removed = client.delete(f"/api/v1/admin/tenants/{tenant_id}", headers=headers)
    assert removed.status_code == 200, removed.text
    assert "preserved" in removed.json()["message"]
    assert client.post("/api/v1/auth/login", json={"username": "updatedtenant", "password": "new-pass-123"}).status_code == 401

    with test_session_factory() as db:
        tenant = db.get(User, tenant_id)
        assert tenant is not None
        assert tenant.room_id is None
        assert tenant.username is None
        assert tenant.password_hash is None
        assert tenant.name == "Updated Tenant"


def test_admin_archives_room_without_losing_meter_history(client, test_session_factory, demo_ids):
    from app.models import ActiveAppliance, ConsumptionLog, Room, User
    from app.security import hash_password

    headers = _admin_headers(client, test_session_factory)
    with test_session_factory() as db:
        tenant = db.get(User, demo_ids["user_id"])
        tenant.name = "Room Tenant"
        tenant.username = "roomtenant"
        tenant.phone = "9992220000"
        tenant.password_hash = hash_password("tenant-pass-123")
        tenant.role = "RESIDENT"
        meter = db.get(Meter, demo_ids["meter_id"])
        db.add(ConsumptionLog(meter_id=meter.id, units_used=Decimal("0.5000"), cost=Decimal("4.00"), balance_after=Decimal("6.00")))
        db.add(ActiveAppliance(meter_id=meter.id, appliance_id="router", appliance_name="Router", watts=12))
        db.add(Recharge(meter_id=meter.id, user_id=tenant.id, amount=Decimal("5.00"), status="SUCCESSFUL"))
        db.commit()
        tenant_id = tenant.id
        meter_id = meter.id
        room_code = db.get(Room, demo_ids["room_id"]).room_code

    refused = client.delete(f"/api/v1/admin/rooms/{demo_ids['room_id']}", headers=headers)
    assert refused.status_code == 409

    removed = client.delete(f"/api/v1/admin/tenants/{tenant_id}", headers=headers)
    assert removed.status_code == 200
    archived = client.delete(f"/api/v1/admin/rooms/{demo_ids['room_id']}", headers=headers)
    assert archived.status_code == 200, archived.text
    assert room_code in archived.json()["message"]

    with test_session_factory() as db:
        room = db.get(Room, demo_ids["room_id"])
        meter = db.get(Meter, meter_id)
        tenant = db.get(User, tenant_id)
        assert room is not None and room.is_active is False and room.room_code == room_code
        assert meter is not None and meter.is_active is False and meter.power_status is False
        assert tenant is not None and tenant.room_id is None and tenant.is_active is False
        assert len(list(db.scalars(select(ConsumptionLog).where(ConsumptionLog.meter_id == meter_id)))) == 1
        assert len(list(db.scalars(select(Recharge).where(Recharge.meter_id == meter_id)))) == 1
        assert len(list(db.scalars(select(WalletLedger).where(WalletLedger.meter_id == meter_id)))) >= 1
        assert list(db.scalars(select(ActiveAppliance).where(ActiveAppliance.meter_id == meter_id))) == []

    assert client.get("/api/v1/meters", headers=headers).json() == []
    assert client.get(f"/api/v1/meters/{meter_id}", headers=headers).status_code == 404
    archived_list = client.get("/api/v1/admin/rooms?include_archived=true", headers=headers)
    assert archived_list.status_code == 200
    archived_room = next(item for item in archived_list.json() if item["id"] == demo_ids["room_id"])
    assert archived_room["is_active"] is False

    restored = client.post(f"/api/v1/admin/rooms/{demo_ids['room_id']}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"] is True
    assert restored.json()["meter"]["is_active"] is True
    with test_session_factory() as db:
        assert db.get(Room, demo_ids["room_id"]).room_code == room_code
        assert db.get(Meter, meter_id).is_active is True
        assert len(list(db.scalars(select(ConsumptionLog).where(ConsumptionLog.meter_id == meter_id)))) == 1


def test_public_identifiers_are_unique_and_stable_across_room_edits(client, test_session_factory, demo_ids):
    headers = _admin_headers(client, test_session_factory)
    original = client.get("/api/v1/admin/rooms", headers=headers)
    assert original.status_code == 200
    room = next(item for item in original.json() if item["id"] == demo_ids["room_id"])
    room_code = room["room_code"]
    meter_code = room["meter"]["meter_code"]
    tenant_code = room["tenants"][0]["tenant_code"]
    assert room_code.startswith("ROM-")
    assert meter_code.startswith("MTR-")
    assert tenant_code.startswith("TEN-")

    created = client.post("/api/v1/admin/rooms", headers=headers, json={
        "room_no": "909", "opening_balance": "50.00", "tariff_per_kwh": "8.0000",
        "first_tenant_name": "New Resident", "first_tenant_username": "newresident",
        "first_tenant_password": "newresident-pass", "first_tenant_phone": "9993330000",
    })
    assert created.status_code == 201, created.text
    assert created.json()["room_code"] != room_code
    assert created.json()["meter"]["meter_code"] != meter_code
    assert created.json()["tenants"][0]["tenant_code"] != tenant_code
    stable = created.json()["room_code"]

    edited = client.patch(f"/api/v1/admin/rooms/{created.json()['id']}", headers=headers, json={
        "room_no": "909A", "tariff_per_kwh": "9.2500",
    })
    assert edited.status_code == 200, edited.text
    assert edited.json()["room_code"] == stable

    second_tenant = client.post(f"/api/v1/admin/rooms/{created.json()['id']}/tenants", headers=headers, json={
        "name": "Another Resident", "username": "anotherresident", "password": "another-pass-123",
    })
    assert second_tenant.status_code == 201, second_tenant.text
    assert second_tenant.json()["tenant_code"].startswith("TEN-")
    assert second_tenant.json()["tenant_code"] != created.json()["tenants"][0]["tenant_code"]



def test_logout_revokes_server_session(client, test_session_factory):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        db.add(User(name="Session Tester", username="sessiontester", password_hash=hash_password("session-pass-123"), role="ADMIN"))
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "sessiontester", "password": "session-pass-123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    revoked = client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401


def test_logout_revokes_only_the_current_users_session(client, test_session_factory):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        db.add_all([
            User(name="Admin One", username="admin-one", password_hash=hash_password("admin-one-pass"), role="ADMIN"),
            User(name="Resident Two", username="resident-two", password_hash=hash_password("resident-two-pass"), role="RESIDENT"),
        ])
        db.commit()
    one = client.post("/api/v1/auth/login", json={"username": "admin-one", "password": "admin-one-pass"})
    two = client.post("/api/v1/auth/login", json={"username": "resident-two", "password": "resident-two-pass"})
    assert one.status_code == two.status_code == 200
    headers_one = {"Authorization": f"Bearer {one.json()['access_token']}"}
    headers_two = {"Authorization": f"Bearer {two.json()['access_token']}"}

    assert client.post("/api/v1/auth/logout", headers=headers_one).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers_one).status_code == 401
    assert client.get("/api/v1/auth/me", headers=headers_two).status_code == 200


def test_meter_endpoints_require_login(client, demo_ids):
    meter_id = demo_ids["meter_id"]
    assert client.get("/api/v1/meters").status_code == 401
    assert client.get(f"/api/v1/meters/{meter_id}").status_code == 401
    assert client.get(f"/api/v1/meters/{meter_id}/report").status_code == 401
    assert client.get("/api/v1/simulation/appliances").status_code == 401
    assert client.get("/api/v1/simulation/scenarios").status_code == 401


def test_resident_cannot_read_another_rooms_meter(client, test_session_factory, demo_ids):
    from app.models import Meter, User
    from app.security import hash_password

    with test_session_factory() as db:
        resident = db.get(User, demo_ids["user_id"])
        resident.username = "scope-resident"
        resident.password_hash = hash_password("resident-pass-123")
        resident.role = "RESIDENT"
        outside_room_id = db.get(User, demo_ids["outside_user_id"]).room_id
        other_meter = Meter(room_id=outside_room_id, current_balance=Decimal("20.00"), power_status=True, tariff_per_kwh=Decimal("8.00"))
        db.add(other_meter); db.commit(); other_meter_id = other_meter.id
    login = client.post("/api/v1/auth/login", json={"username": "scope-resident", "password": "resident-pass-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/v1/meters/{other_meter_id}", headers=headers).status_code == 403
    assert [item["room_id"] for item in client.get("/api/v1/meters", headers=headers).json()] == [demo_ids["room_id"]]


def test_admin_recharge_can_target_each_meter_and_records_actor(client, test_session_factory, demo_ids):
    headers = _admin_headers(client, test_session_factory, username="rechargeadmin")
    created_room = client.post(
        "/api/v1/admin/rooms",
        headers=headers,
        json={"room_no": "303", "tariff_per_kwh": "8.00", "opening_balance": "5.00",
              "first_tenant_name": "Target Tenant", "first_tenant_username": "targettenant",
              "first_tenant_password": "target-tenant-pass", "first_tenant_phone": None},
    )
    assert created_room.status_code == 201, created_room.text
    second = created_room.json()
    second_meter = second["meter"]
    second_tenant = second["tenants"][0]

    targets = client.get("/api/v1/admin/recharge-targets?query=targettenant", headers=headers)
    assert targets.status_code == 200, targets.text
    assert [target["meter_id"] for target in targets.json()] == [second_meter["id"]]
    assert targets.json()[0]["tenants"][0]["tenant_code"] == second_tenant["tenant_code"]

    first = client.post("/api/v1/admin/recharges", headers=headers, json={
        "target_type": "meter_code", "target_value": second_meter["meter_code"],
        "amount": "40.00", "idempotency_key": "admin-recharge-second-meter",
    })
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["meter_id"] == second_meter["id"]
    assert body["actor_name"] == "Admin"
    assert body["actor_user_id"] is not None
    assert body["recharge_code"].startswith("RCH-")
    assert body["tenant_code"] is None

    second_attempt = client.post("/api/v1/admin/recharges", headers=headers, json={
        "target_type": "room_no", "target_value": "303", "amount": "40.00",
        "idempotency_key": "admin-recharge-second-meter",
    })
    assert second_attempt.status_code == 201, second_attempt.text
    assert second_attempt.json()["id"] == body["id"]

    by_tenant = client.post("/api/v1/admin/recharges", headers=headers, json={
        "target_type": "tenant_code", "target_value": second_tenant["tenant_code"],
        "amount": "7.50", "idempotency_key": "admin-recharge-by-tenant",
    })
    assert by_tenant.status_code == 201, by_tenant.text
    assert by_tenant.json()["meter_id"] == second_meter["id"]
    assert by_tenant.json()["tenant_code"] == second_tenant["tenant_code"]

    history = client.get("/api/v1/admin/recharges?query=303&limit=10", headers=headers)
    assert history.status_code == 200, history.text
    assert len(history.json()) == 2
    assert {row["actor_name"] for row in history.json()} == {"Admin"}
    assert {row["recharge_code"] for row in history.json()} == {body["recharge_code"], by_tenant.json()["recharge_code"]}

    with test_session_factory() as db:
        target_meter = db.get(Meter, second_meter["id"])
        original_meter = db.get(Meter, demo_ids["meter_id"])
        assert target_meter.current_balance == Decimal("52.50")
        assert original_meter.current_balance == Decimal("10.00")
        recharges = list(db.scalars(select(Recharge).where(Recharge.meter_id == second_meter["id"])))
        assert len(recharges) == 2
        assert all(r.actor_user_id is not None for r in recharges)
        ledger_entries = list(db.scalars(select(WalletLedger).where(
            WalletLedger.meter_id == second_meter["id"], WalletLedger.entry_type == "RECHARGE"
        )))
        assert len(ledger_entries) == 2
        assert all(entry.actor_user_id == recharges[0].actor_user_id for entry in ledger_entries)
        assert sorted(entry.user_id is None for entry in ledger_entries) == [False, True]


def test_admin_recharge_rejects_reused_key_for_different_request(client, test_session_factory, demo_ids):
    headers = _admin_headers(client, test_session_factory, username="rechargeconflictadmin")
    payload = {"target_type": "room_no", "target_value": "101", "amount": "15.00", "idempotency_key": "admin-key-conflict"}
    first = client.post("/api/v1/admin/recharges", headers=headers, json=payload)
    conflict = client.post("/api/v1/admin/recharges", headers=headers, json={**payload, "amount": "16.00"})
    assert first.status_code == 201, first.text
    assert conflict.status_code == 409
    with test_session_factory() as db:
        assert db.get(Meter, demo_ids["meter_id"]).current_balance == Decimal("25.00")
        assert len(list(db.scalars(select(Recharge).where(Recharge.idempotency_key == "admin-key-conflict")))) == 1


def test_resident_cannot_access_admin_recharge_features(client, resident_headers, demo_ids):
    assert client.get("/api/v1/admin/recharge-targets", headers=resident_headers).status_code == 403
    assert client.get("/api/v1/admin/recharges", headers=resident_headers).status_code == 403
    response = client.post("/api/v1/admin/recharges", headers=resident_headers, json={
        "target_type": "meter_id", "target_value": str(demo_ids["meter_id"]), "amount": "25.00",
    })
    assert response.status_code == 403


def test_admin_can_recharge_an_empty_room_by_room_code(client, test_session_factory):
    headers = _admin_headers(client, test_session_factory, username="emptyroomadmin")
    created = client.post("/api/v1/admin/rooms", headers=headers, json={
        "room_no": "EMPTY-1", "tariff_per_kwh": "8.00", "opening_balance": "0.00",
    })
    assert created.status_code == 201, created.text
    room = created.json()
    response = client.post("/api/v1/admin/recharges", headers=headers, json={
        "target_type": "room_code", "target_value": room["room_code"], "amount": "12.00",
        "idempotency_key": "empty-room-recharge",
    })
    assert response.status_code == 201, response.text
    assert response.json()["meter_id"] == room["meter"]["id"]
    assert response.json()["tenant_code"] is None
    with test_session_factory() as db:
        assert db.get(Meter, room["meter"]["id"]).current_balance == Decimal("12.00")


def test_room_wide_and_private_ticket_visibility_is_enforced(client, test_session_factory, resident_headers, demo_ids):
    from app.models import User
    from app.security import hash_password

    room_ticket = client.post(
        "/api/v1/tickets", headers=resident_headers,
        json={"user_id": demo_ids["user_id"], "issue_type": "METER", "description": "The room meter is making a noise.", "visibility": "ROOM"},
    )
    private_ticket = client.post(
        "/api/v1/tickets", headers=resident_headers,
        json={"user_id": demo_ids["user_id"], "issue_type": "BILLING", "description": "Please review my personal recharge.", "visibility": "PRIVATE"},
    )
    assert room_ticket.status_code == 201, room_ticket.text
    assert private_ticket.status_code == 201, private_ticket.text
    assert room_ticket.json()["ticket_code"].startswith("TKT-")
    assert room_ticket.json()["messages"][0]["message"] == "The room meter is making a noise."
    assert private_ticket.json()["visibility"] == "PRIVATE"

    with test_session_factory() as db:
        room_mate = User(
            name="Room Mate", username="roommate", password_hash=hash_password("roommate-pass"),
            role="RESIDENT", room_id=demo_ids["room_id"],
        )
        db.add(room_mate)
        db.commit()
        roommate_id = room_mate.id

    login = client.post("/api/v1/auth/login", json={"username": "roommate", "password": "roommate-pass"})
    assert login.status_code == 200, login.text
    roommate_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    visible = client.get(f"/api/v1/users/{roommate_id}/tickets", headers=roommate_headers)
    assert visible.status_code == 200, visible.text
    visible_ids = {item["id"] for item in visible.json()}
    assert room_ticket.json()["id"] in visible_ids
    assert private_ticket.json()["id"] not in visible_ids
    assert client.get(f"/api/v1/tickets/{room_ticket.json()['id']}", headers=roommate_headers).status_code == 200
    assert client.get(f"/api/v1/tickets/{private_ticket.json()['id']}", headers=roommate_headers).status_code == 403

    outside_login = client.post("/api/v1/auth/login", json={"username": "otherresident", "password": "resident123"})
    assert outside_login.status_code == 200
    outside_headers = {"Authorization": f"Bearer {outside_login.json()['access_token']}"}
    assert client.get(f"/api/v1/tickets/{room_ticket.json()['id']}", headers=outside_headers).status_code == 403

    with test_session_factory() as db:
        admin = User(name="Support Admin", username="supportadmin", password_hash=hash_password("supportadmin-pass"), role="ADMIN")
        db.add(admin)
        db.commit()
    admin_login = client.post("/api/v1/auth/login", json={"username": "supportadmin", "password": "supportadmin-pass"})
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    all_tickets = client.get("/api/v1/admin/tickets", headers=admin_headers)
    assert all_tickets.status_code == 200, all_tickets.text
    admin_ticket_ids = {item["id"] for item in all_tickets.json()}
    assert room_ticket.json()["id"] in admin_ticket_ids
    assert private_ticket.json()["id"] in admin_ticket_ids


def test_admin_replies_status_workflow_and_resident_reopens_resolved_ticket(client, resident_headers, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    created = client.post(
        "/api/v1/tickets", headers=resident_headers,
        json={"user_id": demo_ids["user_id"], "issue_type": "METER", "description": "My meter status needs review."},
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]
    with test_session_factory() as db:
        db.add(User(name="Resolution Admin", username="resolutionadmin", password_hash=hash_password("resolution-pass"), role="ADMIN"))
        db.commit()
    login = client.post("/api/v1/auth/login", json={"username": "resolutionadmin", "password": "resolution-pass"})
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    premature = client.patch(f"/api/v1/admin/tickets/{ticket_id}", headers=admin_headers, json={"status": "RESOLVED"})
    assert premature.status_code == 409
    reply = client.post(
        f"/api/v1/tickets/{ticket_id}/messages", headers=admin_headers,
        json={"message": "We checked the simulated meter and restored its status."},
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["author_role"] == "ADMIN"
    resolved = client.patch(f"/api/v1/admin/tickets/{ticket_id}", headers=admin_headers, json={"status": "RESOLVED", "priority": "HIGH"})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["priority"] == "HIGH"
    assert any(message["author_role"] == "ADMIN" for message in resolved.json()["messages"])

    reopened = client.post(
        f"/api/v1/tickets/{ticket_id}/messages", headers=resident_headers,
        json={"message": "The issue is still occurring after the suggested fix."},
    )
    assert reopened.status_code == 201, reopened.text
    view = client.get(f"/api/v1/tickets/{ticket_id}", headers=resident_headers)
    assert view.status_code == 200, view.text
    assert view.json()["status"] == "OPEN"
    assert len(view.json()["messages"]) == 3

    closed = client.patch(f"/api/v1/admin/tickets/{ticket_id}", headers=admin_headers, json={"status": "CLOSED"})
    assert closed.status_code == 200, closed.text
    denied_reply = client.post(
        f"/api/v1/tickets/{ticket_id}/messages", headers=resident_headers,
        json={"message": "I cannot reply to a closed ticket."},
    )
    assert denied_reply.status_code == 409


def test_room_wide_tickets_require_room_assignment_and_admin_updates_require_admin(client, test_session_factory):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        user = User(name="Unassigned", username="unassigned", password_hash=hash_password("unassigned-pass"), role="RESIDENT")
        db.add(user)
        db.add(User(name="Admin", username="admin-ticket-test", password_hash=hash_password("admin-pass"), role="ADMIN"))
        db.commit()
    user_login = client.post("/api/v1/auth/login", json={"username": "unassigned", "password": "unassigned-pass"})
    user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
    room_wide = client.post("/api/v1/tickets", headers=user_headers, json={"issue_type": "OTHER", "description": "No room is assigned to me.", "visibility": "ROOM"})
    assert room_wide.status_code == 422
    private = client.post("/api/v1/tickets", headers=user_headers, json={"issue_type": "OTHER", "description": "This is a private request.", "visibility": "PRIVATE"})
    assert private.status_code == 201, private.text
    denied = client.patch(f"/api/v1/admin/tickets/{private.json()['id']}", headers=user_headers, json={"status": "IN_PROGRESS"})
    assert denied.status_code == 403



def test_signed_in_user_can_update_own_profile(client, demo_ids):
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    updated = client.patch("/api/v1/auth/profile", headers=headers, json={"name": "Ishan Updated", "phone": "9876543210"})
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "Ishan Updated"
    assert body["phone"] == "9876543210"
    assert body["tenant_code"].startswith("TEN-")
    assert body["room_id"] == demo_ids["room_id"]

    refreshed = client.get("/api/v1/auth/me", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["name"] == "Ishan Updated"
    assert refreshed.json()["phone"] == "9876543210"


def test_profile_update_rejects_contact_already_used_by_another_account(client, test_session_factory, demo_ids):
    from app.models import User
    from app.security import hash_password

    with test_session_factory() as db:
        db.add(User(name="Phone Owner", username="phone-owner", phone="9000000000", password_hash=hash_password("owner-password"), role="RESIDENT", room_id=demo_ids["room_id"]))
        db.commit()

    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.patch("/api/v1/auth/profile", headers=headers, json={"phone": "9000000000"})
    assert response.status_code == 409


def test_password_change_revokes_all_sessions_and_requires_new_password(client, demo_ids):
    first = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    second = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    assert first.status_code == second.status_code == 200
    first_headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    changed = client.post("/api/v1/auth/change-password", headers=first_headers, json={
        "current_password": "resident123", "new_password": "resident-new-456",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["success"] is True
    assert changed.json()["sessions_revoked"] >= 2
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second_headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident-new-456"}).status_code == 200


def test_profile_and_password_routes_require_authentication(client):
    assert client.patch("/api/v1/auth/profile", json={"name": "Not signed in"}).status_code == 401
    assert client.post("/api/v1/auth/change-password", json={
        "current_password": "old-password", "new_password": "new-password-123",
    }).status_code == 401


def test_password_change_rejects_wrong_current_password(client, demo_ids):
    login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.post("/api/v1/auth/change-password", headers=headers, json={
        "current_password": "wrong-password", "new_password": "resident-new-456",
    })
    assert response.status_code == 400
    assert client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"}).status_code == 200



def test_admin_ticket_buckets_include_historical_closed_tickets(client, test_session_factory, demo_ids):
    from datetime import datetime, timedelta, timezone
    from app.models import SupportTicket

    resident_login = client.post("/api/v1/auth/login", json={"username": "ishan", "password": "resident123"})
    resident_headers = {"Authorization": f"Bearer {resident_login.json()['access_token']}"}
    ticket_ids = []
    for idx in range(3):
        response = client.post("/api/v1/tickets", headers=resident_headers, json={
            "issue_type": "Room support", "description": f"Request number {idx} needs review.",
        })
        assert response.status_code == 201, response.text
        ticket_ids.append(response.json()["id"])

    with test_session_factory() as db:
        db.get(SupportTicket, ticket_ids[0]).status = "CLOSED"
        db.get(SupportTicket, ticket_ids[1]).status = "RESOLVED"
        db.get(SupportTicket, ticket_ids[0]).created_at = datetime.now(timezone.utc) - timedelta(days=400)
        db.commit()

    admin_headers = _admin_headers(client, test_session_factory, username="ticket-bucket-admin")
    pending = client.get("/api/v1/admin/tickets?limit=1&bucket=PENDING", headers=admin_headers)
    closed = client.get("/api/v1/admin/tickets?limit=1&bucket=CLOSED", headers=admin_headers)
    summary = client.get("/api/v1/admin/tickets/summary", headers=admin_headers)
    assert pending.status_code == 200, pending.text
    assert closed.status_code == 200, closed.text
    assert summary.status_code == 200, summary.text
    assert len(pending.json()) == 1 and pending.json()[0]["status"] == "OPEN"
    assert len(closed.json()) == 1 and closed.json()[0]["status"] in {"CLOSED", "RESOLVED"}
    assert summary.json() == {"pending": 1, "closed": 2}


def test_ticket_summary_is_admin_only(client, resident_headers):
    denied = client.get("/api/v1/admin/tickets/summary")
    assert denied.status_code == 403


def test_hourly_usage_report_returns_24_india_local_buckets_and_unallocates_legacy_scenarios(
    client, test_session_factory, resident_headers, demo_ids,
):
    from datetime import date, datetime, time, timezone
    from zoneinfo import ZoneInfo
    from app.models import ConsumptionLog

    india = ZoneInfo("Asia/Kolkata")
    selected_day = date(2026, 10, 15)
    timestamps = [
        datetime.combine(selected_day, time(0, 15), tzinfo=india).astimezone(timezone.utc),
        datetime.combine(selected_day, time(13, 45), tzinfo=india).astimezone(timezone.utc),
        datetime.combine(selected_day, time(23, 59), tzinfo=india).astimezone(timezone.utc),
    ]
    with test_session_factory() as db:
        db.add_all([
            ConsumptionLog(meter_id=demo_ids["meter_id"], units_used=Decimal("0.1000"), cost=Decimal("0.80"), balance_after=Decimal("10.00"), source="MANUAL", created_at=timestamps[0]),
            ConsumptionLog(meter_id=demo_ids["meter_id"], units_used=Decimal("0.2000"), cost=Decimal("1.60"), balance_after=Decimal("10.00"), source="LIVE", created_at=timestamps[1]),
            ConsumptionLog(meter_id=demo_ids["meter_id"], units_used=Decimal("0.3000"), cost=Decimal("2.40"), balance_after=Decimal("10.00"), source="MANUAL", created_at=timestamps[2]),
            # Old scenario rows represented a whole schedule block, not one hour.
            ConsumptionLog(meter_id=demo_ids["meter_id"], units_used=Decimal("1.0000"), cost=Decimal("8.00"), balance_after=Decimal("10.00"), source="SCENARIO_HISTORY", created_at=timestamps[0]),
            # Seeded demo history was a daily aggregate saved at an arbitrary time.
            ConsumptionLog(meter_id=demo_ids["meter_id"], units_used=Decimal("0.4000"), cost=Decimal("3.20"), balance_after=Decimal("10.00"), source="HISTORICAL", note="Seeded demo usage history", created_at=timestamps[0]),
        ])
        db.commit()

    response = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/report?granularity=hourly&date={selected_day.isoformat()}",
        headers=resident_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["granularity"] == "hourly"
    assert body["timezone"] == "Asia/Kolkata"
    assert body["selected_date"] == selected_day.isoformat()
    assert len(body["hourly"]) == 24
    assert body["hourly"][0]["label"] == "12 AM–1 AM"
    assert body["hourly"][23]["label"] == "11 PM–12 AM"
    assert body["hourly"][0]["units_used"] == "0.1000"
    assert body["hourly"][13]["units_used"] == "0.2000"
    assert body["hourly"][23]["units_used"] == "0.3000"
    assert body["total_units"] == "2.0000"
    assert body["total_cost"] == "16.00"
    assert body["unallocated_units"] == "1.4000"
    assert body["unallocated_cost"] == "11.20"
    assert body["unallocated_reading_count"] == 2
    assert body["hourly_data_quality"] == "MIXED"

    # The same midnight-boundary readings must appear under the India-local date
    # in daily analytics rather than the previous UTC calendar day.
    daily = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/report?period=7d",
        headers=resident_headers,
    )
    assert daily.status_code == 200, daily.text
    assert selected_day.isoformat() in {item["date"] for item in daily.json()["daily"]}


def test_hourly_usage_report_rejects_future_date(client, resident_headers, demo_ids):
    response = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/report?granularity=hourly&date=2999-01-01",
        headers=resident_headers,
    )
    assert response.status_code == 422


def test_scenario_history_is_split_at_hour_boundaries_without_changing_total(client, resident_headers, test_session_factory, demo_ids):
    from datetime import date, timedelta
    from app.models import ConsumptionLog, SimulationScenario

    historical_day = date.today() - timedelta(days=3)
    with test_session_factory() as db:
        scenario = SimulationScenario(
            slug="hourly-split-test", name="Hourly split test", audience="RESIDENT",
            description="Block crossing one hour boundary", is_builtin=True,
            blocks=[{"label": "Fan crosses hour", "start_min": 30, "end_min": 120, "appliance_ids": ["fan"]}],
        )
        db.add(scenario)
        db.commit()
        scenario_id = scenario.id

    response = client.post(
        f"/api/v1/simulation/scenarios/{scenario_id}/apply",
        headers=resident_headers,
        json={"meter_id": demo_ids["meter_id"], "simulation_date": historical_day.isoformat()},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["historical_only"] is True
    assert result["reading_count"] == 2
    assert Decimal(result["units_used"]) == Decimal("0.1125")
    assert Decimal(result["cost"]) == Decimal("0.90")

    hourly = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/report?granularity=hourly&date={historical_day.isoformat()}",
        headers=resident_headers,
    )
    assert hourly.status_code == 200, hourly.text
    bins = hourly.json()["hourly"]
    assert Decimal(bins[0]["units_used"]) == Decimal("0.0375")
    assert Decimal(bins[1]["units_used"]) == Decimal("0.0750")
    assert Decimal(bins[0]["cost"]) + Decimal(bins[1]["cost"]) == Decimal("0.90")

    with test_session_factory() as db:
        new_rows = list(db.scalars(
            select(ConsumptionLog).where(
                ConsumptionLog.meter_id == demo_ids["meter_id"],
                ConsumptionLog.source == "SCENARIO_HOURLY_HISTORY",
            )
        ).all())
        assert sum((Decimal(row.units_used) for row in new_rows), Decimal("0")) == Decimal("0.1125")
        assert sum((Decimal(row.cost) for row in new_rows), Decimal("0")) == Decimal("0.90")


def test_usage_report_returns_configured_environmental_estimate(client, resident_headers, demo_ids):
    created = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/readings",
        headers=resident_headers,
        json={"units_used": "0.5000"},
    )
    assert created.status_code == 201, created.text
    report = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/report?period=7d",
        headers=resident_headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["co2_factor_kg_per_kwh"] == "0.675"
    assert body["estimated_co2_kg"] == "0.338"
    assert body["tree_years_equivalent"] == "0.0154"
    assert "Version 22.0" in body["co2_factor_source"]
    assert body["co2_factor_source_url"].startswith("https://")


def test_usage_export_csv_contains_meter_metadata_and_totals(client, resident_headers, demo_ids):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    created = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/readings",
        headers=resident_headers,
        json={"units_used": "0.5000"},
    )
    assert created.status_code == 201, created.text
    day = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    response = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/usage-export?start_date={day}&end_date={day}",
        headers=resident_headers,
    )
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=\"smartvolt-usage-" in response.headers["content-disposition"]
    assert "SmartVolt consumption export" in response.text
    assert "Recorded consumption (kWh),0.5000" in response.text
    assert "Recorded energy cost (INR),4.00" in response.text
    assert "Timestamp (Asia/Kolkata)" in response.text


def test_usage_export_rejects_invalid_date_range(client, resident_headers, demo_ids):
    response = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/usage-export?start_date=2026-10-10&end_date=2026-10-01",
        headers=resident_headers,
    )
    assert response.status_code == 422


def test_monthly_billing_statement_summarizes_recharges_and_consumption(client, resident_headers, demo_ids):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    recharge = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/recharges",
        headers=resident_headers,
        json={"user_id": demo_ids["user_id"], "amount": "25.00", "idempotency_key": "statement-recharge"},
    )
    assert recharge.status_code == 201, recharge.text
    usage = client.post(
        f"/api/v1/meters/{demo_ids['meter_id']}/readings",
        headers=resident_headers,
        json={"units_used": "0.5000"},
    )
    assert usage.status_code == 201, usage.text
    month = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m")
    response = client.get(
        f"/api/v1/meters/{demo_ids['meter_id']}/billing-statement?month={month}",
        headers=resident_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["month"] == month
    assert body["total_units"] == "0.5000"
    assert body["total_energy_cost"] == "4.00"
    assert body["total_recharge_amount"] == "25.00"
    assert body["recharge_count"] == 1
    assert body["reading_count"] == 1
    assert body["meter_code"]
    assert body["opening_balance"] == "0.00"
    assert body["closing_balance"] == "31.00"


def test_usage_export_does_not_allow_another_room_meter(client, resident_headers, test_session_factory, demo_ids):
    from app.models import Meter, Room

    with test_session_factory() as db:
        # Add a meter in another room so the resident access boundary can be tested.
        other_room = Room(room_no="303")
        db.add(other_room)
        db.flush()
        outside_meter = Meter(room_id=other_room.id, current_balance=Decimal("10.00"))
        db.add(outside_meter)
        db.commit()
        outside_meter_id = outside_meter.id
    response = client.get(
        f"/api/v1/meters/{outside_meter_id}/usage-export?start_date=2026-10-01&end_date=2026-10-16",
        headers=resident_headers,
    )
    assert response.status_code == 403
