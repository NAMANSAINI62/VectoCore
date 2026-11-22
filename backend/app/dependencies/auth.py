"""Authentication dependencies for verifying JWT and injecting authenticated user."""

import uuid
from fastapi import Cookie, Depends, Header
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import security
from app.core.exceptions import AuthenticationError, InactiveUserError, TokenExpiredError
from app.database.session import get_db_session
from app.models.user import User
from app.repositories.user_repository import UserRepository


async def get_token_from_header_or_cookie(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> str:
    """Extract JWT token from Bearer Authorization header or HttpOnly cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    if access_token:
        return access_token
    raise AuthenticationError(detail="Missing authentication credentials")


async def get_current_user(
    token: str = Depends(get_token_from_header_or_cookie),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Validate JWT access token and return active authenticated user entity.
    Reusable dependency across protected endpoints.
    """
    try:
        payload = security.decode_access_token(token)
    except ExpiredSignatureError:
        raise TokenExpiredError()
    except PyJWTError:
        raise AuthenticationError(detail="Could not validate credentials")

    subject = payload.get("sub")
    token_type = payload.get("type")

    if not subject or token_type != "access":
        raise AuthenticationError(detail="Invalid token payload")

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise AuthenticationError(detail="Malformed user identifier in token")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise AuthenticationError(detail="User no longer exists")

    if not user.is_active:
        raise InactiveUserError()

    return user
