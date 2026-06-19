"""Auth: PBKDF2 password hashing (stdlib, no native deps) + JWT bearer tokens."""
import hashlib
import os
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)

MIN_PASSWORD_LEN = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + dk.hex()


def unusable_password() -> str:
    """A hash that no password can match — for invited users who haven't set one yet."""
    return "!" + secrets.token_hex(32)


def new_reset_token() -> str:
    """A URL-safe one-time token for invite / password-reset links."""
    return secrets.token_urlsafe(32)


def validate_new_password(new: str, confirm: str) -> None:
    """Shared policy for any self-set password. Raises HTTP 400 on failure."""
    new = new or ""
    if len(new) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LEN} characters")
    if new != (confirm or ""):
        raise HTTPException(400, "Passwords don't match")


def _pwd_version(user: User) -> int:
    """A monotonically-changing stamp tied to the last password change, embedded in the JWT
    so that changing/resetting a password invalidates tokens issued beforehand."""
    pca = getattr(user, "password_changed_at", None)
    return int(pca.timestamp()) if pca else 0


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "pv": _pwd_version(user),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    # If the token carries a password-version, it must still match — a password change/reset
    # bumps the version and invalidates tokens minted before it. (Older tokens lack "pv" and
    # are honoured until they expire, so this rolls out without forcing everyone to re-login.)
    if "pv" in payload and payload.get("pv") != _pwd_version(user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid — please sign in again")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def require_manager(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Admins, or anyone whose SalesIQ role resolves to 'manager', may manage users."""
    if user.role == "admin":
        return user
    from .services.salesiq.roles import role_for_user
    if role_for_user(db, user) == "manager":
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager access required")


def require_analyst(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "analyst"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Analyst access required")
    return user
