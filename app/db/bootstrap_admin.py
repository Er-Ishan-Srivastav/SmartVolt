"""Create the first administrator without installing development demo accounts.

Run after database migrations on a new production database:
    python -m app.db.bootstrap_admin

This command never prints or changes an existing administrator's password.
"""

from sqlalchemy import func, select

from app.core import settings
from app.db.session import SessionLocal
from app.models import User
from app.security import hash_password


def bootstrap_admin() -> bool:
    """Create the configured administrator only when the username is unused.

    Returns True when a new admin was created, False when that admin already exists.
    Production runs require non-demo credentials and a high-entropy application secret.
    """
    username = settings.admin_username.strip()
    password = settings.admin_password
    secret = settings.auth_secret

    if not username:
        raise ValueError("ADMIN_USERNAME must not be empty")
    if settings.environment.lower() == "production":
        if len(password) < 16 or password in {"Admin123!", "REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD"}:
            raise ValueError("Production ADMIN_PASSWORD must be unique and at least 16 characters")
        if len(secret) < 32 or secret == "local-development-secret-change-before-deployment":
            raise ValueError("Production AUTH_SECRET must be a high-entropy secret of at least 32 characters")

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if existing is not None:
            if existing.role != "ADMIN" or not existing.is_active:
                raise ValueError("Configured administrator username is already assigned to a non-admin/inactive account")
            print(f"Administrator '{username}' already exists; no account or password changes made.")
            return False

        admin = User(
            name="SmartVolt Administrator",
            username=username,
            password_hash=hash_password(password),
            role="ADMIN",
            room_id=None,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Administrator '{username}' created successfully. No password was displayed.")
        return True


def main() -> None:
    bootstrap_admin()


if __name__ == "__main__":
    main()
