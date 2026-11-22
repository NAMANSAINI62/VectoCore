"""User profile API endpoints for authenticated users."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserProfileUpdate, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile data of currently logged in user."""
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update authenticated user profile",
)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update profile attributes for currently logged in user."""
    service = UserService(db)
    updated_user = await service.update_profile(
        user=current_user,
        full_name=payload.full_name,
    )
    return UserResponse.model_validate(updated_user)
