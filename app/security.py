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

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import settings
from app.db.session import get_db
from app.models import User

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


def issue_access_token(user: User) -> str:
    payload = _b64(json.dumps({"sub": user.id, "role": user.role, "exp": int(time.time()) + 8 * 3600}, separators=(",", ":")).encode())
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
        if not isinstance(claims.get("sub"), int) or claims.get("role") not in {"ADMIN", "RESIDENT"}:
            return None
        return claims
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials)
    user = db.get(User, claims["sub"]) if claims else None
    if user is None or user.role != claims.get("role") or not user.username or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve an optional demo user for public read/simulation flows."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    claims = decode_access_token(credentials.credentials)
    user = db.get(User, claims["sub"]) if claims else None
    if user is None or user.role != claims.get("role") or not user.username or not user.password_hash:
        return None
    return user
