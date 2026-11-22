"""Session database repository for refresh token lifecycle and rotation."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_session import UserSession


class SessionRepository:
    """Encapsulates all database operations on user sessions and refresh tokens."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
    ) -> UserSession:
        """Create new active user session."""
        session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        """Find session record by its hashed refresh token."""
        stmt = select(UserSession).where(UserSession.token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_session(self, session: UserSession) -> None:
        """Mark single session as revoked."""
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        """Revoke all sessions belonging to token family (replay attack defense)."""
        stmt = (
            update(UserSession)
            .where(UserSession.family_id == family_id)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> None:
        """Revoke all active sessions for a user (e.g. after password reset)."""
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        await self.db.commit()
