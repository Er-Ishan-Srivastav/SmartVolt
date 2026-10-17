from sqlalchemy import select

from app.core import settings
from app.db import bootstrap_admin
from app.models import User
from app.security import verify_password


def test_bootstrap_creates_only_configured_admin(test_session_factory, monkeypatch):
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", test_session_factory)
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "admin_username", "release-admin")
    monkeypatch.setattr(settings, "admin_password", "local-bootstrap-password")

    assert bootstrap_admin.bootstrap_admin() is True
    assert bootstrap_admin.bootstrap_admin() is False

    with test_session_factory() as db:
        admin = db.scalar(select(User).where(User.username == "release-admin"))
        assert admin is not None
        assert admin.role == "ADMIN"
        assert admin.room_id is None
        assert admin.is_active is True
        assert admin.tenant_code is None
        assert verify_password("local-bootstrap-password", admin.password_hash)
        assert db.scalar(select(User.id).where(User.username == "ishan")) is None


def test_production_bootstrap_rejects_demo_password(test_session_factory, monkeypatch):
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", test_session_factory)
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_username", "release-admin")
    monkeypatch.setattr(settings, "admin_password", "Admin123!")
    monkeypatch.setattr(settings, "auth_secret", "x" * 64)

    try:
        bootstrap_admin.bootstrap_admin()
    except ValueError as exc:
        assert "ADMIN_PASSWORD" in str(exc)
    else:
        raise AssertionError("Expected weak production password to be rejected")
