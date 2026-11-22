"""Authentication service implementing core authentication business logic."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.core import security
from app.core.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    SessionRevokedError,
    TokenExpiredError,
    UserAlreadyExistsError,
)
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Orchestrates user registration, authentication, session renewal, and logout."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)

    async def register(self, full_name: str, email: str, password: str) -> User:
        """Register a new user account with hashed password."""
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise UserAlreadyExistsError()

        hashed_pw = security.hash_password(password)
        user = await self.user_repo.create(
            full_name=full_name,
            email=email,
            password_hash=hashed_pw,
        )
        logger.info(f"User registered successfully: {user.id}")
        return user

    async def authenticate(self, email: str, password: str) -> tuple[User, str, str]:
        """
        Authenticate user credentials.
        Returns (user, access_token, raw_refresh_token).
        """
        user = await self.user_repo.get_by_email(email)
        if not user or not security.verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        # Generate Access Token
        access_token = security.create_access_token(subject=str(user.id))

        # Generate Refresh Token and Session
        raw_refresh_token = security.generate_random_token(64)
        token_hash = security.hash_token(raw_refresh_token)
        family_id = uuid.uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.session_repo.create_session(
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
        )

        logger.info(f"User logged in: {user.id}")
        return user, access_token, raw_refresh_token

    async def refresh_session(self, raw_refresh_token: str) -> tuple[str, str]:
        """
        Rotate refresh token and issue fresh access token.
        Detects replay attacks: if an already-revoked token is presented, revoke the entire family.
        Returns (new_access_token, new_raw_refresh_token).
        """
        token_hash = security.hash_token(raw_refresh_token)
        session = await self.session_repo.get_by_token_hash(token_hash)

        if not session:
            raise SessionRevokedError()

        # REPLAY ATTACK DETECTION
        if session.revoked_at is not None:
            logger.warning(
                f"Refresh token reuse detected for user {session.user_id}! Revoking token family {session.family_id}."
            )
            await self.session_repo.revoke_family(session.family_id)
            raise SessionRevokedError()

        # Check token expiration
        now = datetime.now(timezone.utc)
        if session.expires_at < now:
            await self.session_repo.revoke_session(session)
            raise TokenExpiredError()

        # Verify associated user account
        user = await self.user_repo.get_by_id(session.user_id)
        if not user or not user.is_active:
            await self.session_repo.revoke_session(session)
            raise InactiveUserError()

        # Revoke the current token in the rotation chain
        await self.session_repo.revoke_session(session)

        # Issue new token pair preserving the family_id
        new_raw_refresh = security.generate_random_token(64)
        new_token_hash = security.hash_token(new_raw_refresh)
        new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.session_repo.create_session(
            user_id=user.id,
            token_hash=new_token_hash,
            family_id=session.family_id,
            expires_at=new_expires_at,
        )

        new_access_token = security.create_access_token(subject=str(user.id))
        return new_access_token, new_raw_refresh

    async def logout(self, raw_refresh_token: str | None) -> None:
        """Revoke active session upon user logout."""
        if raw_refresh_token:
            token_hash = security.hash_token(raw_refresh_token)
            session = await self.session_repo.get_by_token_hash(token_hash)
            if session and session.revoked_at is None:
                await self.session_repo.revoke_session(session)
                logger.info(f"Session revoked for user: {session.user_id}")
