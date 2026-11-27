"""User service for profile management."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    """Service handling profile operations for authenticated users."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def update_profile(self, user: User, full_name: str | None = None) -> User:
        """Update authenticated user profile fields."""
        return await self.user_repo.update_profile(user=user, full_name=full_name)
