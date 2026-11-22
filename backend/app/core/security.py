"""Security module: Argon2id password hashing, JWT generation, and token helpers."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from pwdlib import PasswordHash
from app.config.settings import get_settings

settings = get_settings()

# Modern Argon2id password hasher (recommended by OWASP)
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash plain password using Argon2id."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Generate signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT access token."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "exp", "iat", "type"]},
    )


def generate_random_token(length: int = 64) -> str:
    """Generate cryptographically secure URL-safe random string."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Compute deterministic SHA-256 hash of token for safe DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
