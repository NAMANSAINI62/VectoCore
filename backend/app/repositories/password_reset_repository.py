"""Password reset repository for managing recovery tokens in PostgreSQL."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.password_reset import PasswordResetToken


class PasswordResetRepository:
    """Encapsulates all database operations on password reset tokens."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        """Create new single-use password reset record."""
        record = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Retrieve token record by its hash."""
        stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token_record: PasswordResetToken) -> None:
        """Mark token as consumed."""
        token_record.used_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def invalidate_user_tokens(self, user_id: uuid.UUID) -> None:
        """Invalidate any existing unused tokens for a user."""
        stmt = (
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .where(PasswordResetToken.used_at.is_(None))
            .values(used_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        await self.db.commit()
