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
