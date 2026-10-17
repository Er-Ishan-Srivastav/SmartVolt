"""Small dependency-free password hashing and signed demo access tokens.

Tokens are suitable for this local simulation. Use a managed identity provider or
reviewed JWT/session library before production deployment.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import settings
from app.db.session import get_db
from app.models import AuthSession, User

_ITERATIONS = 310_000
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


SESSION_TTL_SECONDS = 8 * 60 * 60


def issue_access_token(user: User, db: Session) -> str:
    """Create a signed bearer token backed by a revocable database session."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    session_id = secrets.token_urlsafe(32)
    db.add(AuthSession(
        session_id=session_id, user_id=user.id, created_at=now, expires_at=expires_at, revoked_at=None,
    ))
    payload = _b64(json.dumps({
        "sub": user.id, "role": user.role, "sid": session_id, "exp": int(expires_at.timestamp()),
    }, separators=(",", ":")).encode())
    signature = hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(signature)}"


def decode_access_token(token: str) -> dict[str, object] | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if int(claims.get("exp", 0)) <= int(time.time()):
            return None
        if (not isinstance(claims.get("sub"), int)
                or claims.get("role") not in {"ADMIN", "RESIDENT"}
                or not isinstance(claims.get("sid"), str)):
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _active_session(claims: dict[str, object], db: Session) -> AuthSession | None:
    session = db.get(AuthSession, claims["sid"])
    if session is None or session.user_id != claims["sub"] or session.revoked_at is not None:
        return None
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        return None
    return session


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials)
    session = _active_session(claims, db) if claims else None
    user = db.get(User, claims["sub"]) if claims and session else None
    if user is None or not user.is_active or user.role != claims.get("role") or not user.username or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve a valid, non-revoked optional session."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    claims = decode_access_token(credentials.credentials)
    if not claims or not _active_session(claims, db):
        return None
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active or user.role != claims.get("role") or not user.username or not user.password_hash:
        return None
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user
