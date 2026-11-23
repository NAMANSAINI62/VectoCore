"""Password reset service orchestrating recovery tokens and password updates."""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.core import security
from app.core.exceptions import InvalidResetTokenError
from app.repositories.reset_token_repo import PasswordResetRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
settings = get_settings()


class PasswordResetService:
    """Service handling password recovery initiation and execution."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.reset_repo = PasswordResetRepository(db)
        self.session_repo = SessionRepository(db)

    async def request_password_reset(self, email: str) -> str | None:
        """
        Create password reset token for given email.
        Always returns generic confirmation to prevent user enumeration attacks.
        Returns raw recovery token if user exists (to send via email/notifier).
        """
        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            # Silently return to prevent user enumeration
            return None

        # Invalidate any previously pending reset tokens
        await self.reset_repo.invalidate_user_tokens(user.id)

        raw_token = security.generate_random_token(48)
        token_hash = security.hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )

        await self.reset_repo.create_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        logger.info(f"Password reset token issued for user: {user.id}")
        return raw_token

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Verify token and update password, revoking all existing user sessions."""
        token_hash = security.hash_token(raw_token)
        token_record = await self.reset_repo.get_by_token_hash(token_hash)

        now = datetime.now(timezone.utc)
        if not token_record or token_record.used_at is not None or token_record.expires_at < now:
            raise InvalidResetTokenError()

        user = await self.user_repo.get_by_id(token_record.user_id)
        if not user or not user.is_active:
            raise InvalidResetTokenError()

        # Update password hash
        new_hash = security.hash_password(new_password)
        await self.user_repo.update_password(user, new_hash)

        # Mark token as used
        await self.reset_repo.mark_used(token_record)

        # Invalidate all user sessions to secure the account
        await self.session_repo.revoke_all_user_sessions(user.id)
        logger.info(f"Password successfully reset for user: {user.id}")
