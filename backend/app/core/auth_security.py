"""
app/core/auth_security.py

JWT token creation/validation and password hashing for user auth.
Uses HS256 JWT (via PyJWT) and bcrypt directly.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt

from app.config import settings

# ── Password helpers using bcrypt directly ────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return bcrypt hash of the plain-text password."""
    pw_bytes = plain.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pw_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of plain password against its hash."""
    try:
        pw_bytes = plain.encode('utf-8')
        hash_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    role: str,
    extra: Optional[dict] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create a signed JWT access token.
    """
    if expires_minutes is None:
        expires_minutes = settings.JWT_EXPIRE_MINUTES

    now_dt = datetime.now(timezone.utc)
    expire_dt = now_dt + timedelta(minutes=expires_minutes)

    payload = {
        "sub": subject,
        "role": role,
        "exp": int(expire_dt.timestamp()),
        "iat": int(now_dt.timestamp()),
    }
    if extra:
        payload.update(extra)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def create_reset_token(email: str) -> str:
    """
    Create a short-lived (15 min) single-use password-reset token.
    """
    now_dt = datetime.now(timezone.utc)
    expire_dt = now_dt + timedelta(minutes=15)
    payload = {
        "sub": email,
        "purpose": "password_reset",
        "exp": int(expire_dt.timestamp()),
        "iat": int(now_dt.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_reset_token(token: str) -> Optional[str]:
    """
    Decode a password-reset token. Returns the email on success, None on failure.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            return None
        return payload.get("sub")
    except Exception:
        return None
