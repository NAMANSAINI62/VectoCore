"""Authentication API endpoints: register, login, refresh, logout, me, and password recovery."""

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.database.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.password_reset_service import PasswordResetService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """Set secure HttpOnly cookies for access and refresh tokens."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",  # Scoped path for refresh cookies
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear access and refresh authentication cookies."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Create a new user account with secure password hashing."""
    service = AuthService(db)
    user = await service.register(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive access token + session cookies",
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Verify credentials and set secure HttpOnly cookies."""
    service = AuthService(db)
    _, access_token, refresh_token = await service.authenticate(
        email=payload.email,
        password=payload.password,
    )
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Renew access token using rotated refresh token",
)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    """Rotate refresh token and issue fresh access token."""
    if not refresh_token:
        from app.core.exceptions import AuthenticationError
        raise AuthenticationError(detail="Missing refresh token cookie")

    service = AuthService(db)
    new_access_token, new_refresh_token = await service.refresh_session(refresh_token)
    _set_auth_cookies(response, new_access_token, new_refresh_token)
    return RefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke session and clear authentication cookies",
)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Revoke active session and delete auth cookies."""
    service = AuthService(db)
    await service.logout(refresh_token)
    _clear_auth_cookies(response)
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get currently authenticated user identity",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return identity of the authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password recovery token",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """
    Generate recovery token for email. Always returns a generic confirmation message
    to prevent user account enumeration.
    """
    service = PasswordResetService(db)
    _ = await service.request_password_reset(payload.email)
    return MessageResponse(
        message="If this email is registered, you will receive password reset instructions."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using recovery token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Verify recovery token and apply new password."""
    service = PasswordResetService(db)
    await service.reset_password(
        raw_token=payload.token,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password has been reset successfully. Please log in.")
