"""User database repository for PostgreSQL operations."""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User


class UserRepository:
    """Encapsulates all database operations on users."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch user by primary key UUID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch user by case-insensitive normalized email."""
        stmt = select(User).where(User.email == email.strip().lower())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        """Fetch user by Google OAuth subject identifier."""
        stmt = select(User).where(User.google_sub == google_sub)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, full_name: str, email: str, password_hash: str) -> User:
        """Insert new local user record into database."""
        user = User(
            full_name=full_name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            auth_provider="local",
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_passwordless(
        self,
        *,
        full_name: str,
        email: str,
        auth_provider: str,
        google_sub: str | None = None,
        is_verified: bool = True,
    ) -> User:
        """Insert a passwordless user authenticated via Google OAuth or Email OTP."""
        user = User(
            full_name=full_name.strip()[:150] or email.split("@")[0],
            email=email.strip().lower(),
            password_hash=None,
            auth_provider=auth_provider,
            google_sub=google_sub,
            is_active=True,
            is_verified=is_verified,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_profile(self, user: User, full_name: str | None = None) -> User:
        """Update profile fields on user."""
        if full_name is not None:
            user.full_name = full_name.strip()
        await self.db.commit()
        await self.db.refresh(user)
        return user
