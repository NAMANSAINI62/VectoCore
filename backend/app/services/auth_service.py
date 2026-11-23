"""Authentication service implementing core authentication business logic."""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
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
from app.models.auth_otp import AuthOtp
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import is_smtp_configured, send_otp_email

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

    async def _issue_session_tokens(self, user: User) -> tuple[User, str, str]:
        """Issue a JWT access token and persist a rotated refresh token session."""
        if not user.is_active:
            raise InactiveUserError()

        access_token = security.create_access_token(subject=str(user.id))
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
        return user, access_token, raw_refresh_token

    async def authenticate(self, email: str, password: str) -> tuple[User, str, str]:
        """
        Authenticate user credentials.
        Returns (user, access_token, raw_refresh_token).
        """
        user = await self.user_repo.get_by_email(email)
        if not user or not user.password_hash or not security.verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        logger.info(f"User logged in: {user.id}")
        return await self._issue_session_tokens(user)

    async def authenticate_google(
        self,
        *,
        google_sub: str,
        email: str,
        full_name: str,
        email_verified: bool,
    ) -> tuple[User, str, str]:
        """Authenticate or auto-provision a user verified by Google OAuth."""
        norm_email = email.strip().lower()
        user = await self.user_repo.get_by_google_sub(google_sub)
        if user is None:
            user = await self.user_repo.get_by_email(norm_email)
            if user is not None:
                user.google_sub = google_sub
                if email_verified:
                    user.is_verified = True
                if not user.full_name and full_name:
                    user.full_name = full_name.strip()[:150]
                await self.db.commit()
                await self.db.refresh(user)
            else:
                user = await self.user_repo.create_passwordless(
                    full_name=full_name or norm_email.split("@")[0],
                    email=norm_email,
                    auth_provider="google",
                    google_sub=google_sub,
                    is_verified=email_verified,
                )
        logger.info(f"User logged in via Google OAuth: {user.id}")
        return await self._issue_session_tokens(user)

    @staticmethod
    def _hash_otp(email: str, code: str) -> str:
        msg = f"{email.strip().lower()}:{code.strip()}".encode("utf-8")
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    async def _create_and_hash_otp(self, norm_email: str) -> str:
        """Rate-limit, invalidate prior codes, and persist a fresh 6-digit HMAC-hashed OTP."""
        if not is_smtp_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email OTP is not configured yet. Add SMTP_HOST, SMTP_USER, and SMTP_PASSWORD to backend/.env.",
            )
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=10)
        recent_count = await self.db.scalar(
            select(func.count())
            .select_from(AuthOtp)
            .where(AuthOtp.email == norm_email, AuthOtp.created_at >= window_start)
        )
        if (recent_count or 0) >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests. Please wait a few minutes before requesting another code.",
            )

        await self.db.execute(
            update(AuthOtp)
            .where(AuthOtp.email == norm_email, AuthOtp.consumed_at.is_(None))
            .values(consumed_at=now)
        )

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp_row = AuthOtp(
            email=norm_email,
            otp_hash=self._hash_otp(norm_email, code),
            attempts=0,
            expires_at=now + timedelta(minutes=5),
        )
        self.db.add(otp_row)
        await self.db.commit()
        return code

    async def _verify_and_consume_otp(self, email: str, code: str) -> str:
        """Verify a 6-digit OTP against the latest unconsumed hash and mark it consumed."""
        norm_email = email.strip().lower()
        now = datetime.now(timezone.utc)
        otp_row = await self.db.scalar(
            select(AuthOtp)
            .where(AuthOtp.email == norm_email, AuthOtp.consumed_at.is_(None))
            .order_by(AuthOtp.created_at.desc())
            .limit(1)
        )
        if otp_row is None or otp_row.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OTP expired or not found. Please request a new code.",
            )

        if otp_row.attempts >= 5:
            otp_row.consumed_at = now
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many incorrect attempts. Please request a new OTP code.",
            )

        expected_hash = self._hash_otp(norm_email, code)
        if not hmac.compare_digest(expected_hash, otp_row.otp_hash):
            otp_row.attempts += 1
            await self.db.commit()
            remaining = max(0, 5 - otp_row.attempts)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid OTP code. {remaining} attempt(s) remaining.",
            )

        otp_row.consumed_at = now
        await self.db.commit()
        return norm_email

    async def prepare_email_otp(self, email: str) -> str:
        """Create and persist a 6-digit login OTP so the endpoint can dispatch SMTP in the background."""
        return await self._create_and_hash_otp(email.strip().lower())

    async def request_email_otp(self, email: str) -> None:
        """Generate, hash, store, and email a 6-digit passwordless OTP."""
        norm_email = email.strip().lower()
        code = await self._create_and_hash_otp(norm_email)
        await send_otp_email(norm_email, code, expire_minutes=5)

    async def verify_email_otp(self, email: str, code: str) -> tuple[User, str, str]:
        """Verify a 6-digit email OTP, auto-create the user if needed, and issue session tokens."""
        norm_email = await self._verify_and_consume_otp(email, code)

        user = await self.user_repo.get_by_email(norm_email)
        if user is None:
            user = await self.user_repo.create_passwordless(
                full_name=norm_email.split("@")[0],
                email=norm_email,
                auth_provider="email_otp",
                is_verified=True,
            )
        elif not user.is_verified:
            user.is_verified = True
            await self.db.commit()
            await self.db.refresh(user)

        logger.info(f"User logged in via Email OTP: {user.id}")
        return await self._issue_session_tokens(user)

    async def prepare_password_reset_otp(self, email: str) -> str | None:
        """Create a 6-digit password reset OTP if the active user exists (returns None otherwise)."""
        norm_email = email.strip().lower()
        user = await self.user_repo.get_by_email(norm_email)
        if user is None or not user.is_active:
            return None
        return await self._create_and_hash_otp(norm_email)

    async def reset_password_with_otp(self, email: str, code: str, new_password: str) -> None:
        """Verify a 6-digit OTP and set a new hashed password on the user account."""
        norm_email = await self._verify_and_consume_otp(email, code)
        user = await self.user_repo.get_by_email(norm_email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found.",
            )
        user.password_hash = security.hash_password(new_password)
        user.is_verified = True
        await self.db.commit()
        await self.session_repo.revoke_all_user_sessions(user.id)
        logger.info(f"Password reset via OTP for user: {user.id}")

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
