"""Authentication API endpoints: register, login, refresh, logout, me, and password recovery."""

import hashlib
import hmac
import logging
import secrets
import time
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.core.exceptions import AuthenticationError
from app.database.session import get_db_session
from app.dependencies.auth import get_current_user
from app.guardrails.rate_limiter import RedisRateLimiter
from app.models.user import User
from app.schemas.auth import (
    AuthMethodsResponse,
    ChangePasswordRequest,
    EmailOtpRequest,
    EmailOtpVerifyRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetOtpRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.services.email_service import is_smtp_configured, send_otp_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


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


def _issue_token_response(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> TokenResponse:
    """Set HttpOnly auth cookies and return the standardized token payload."""
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Create a new user account with secure password hashing."""
    await RedisRateLimiter().check_endpoint_limit("auth_register", _client_ip(request), limit_per_min=5)
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
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Verify credentials and set secure HttpOnly cookies."""
    await RedisRateLimiter().check_endpoint_limit("auth_login", _client_ip(request), limit_per_min=5)
    service = AuthService(db)
    _, access_token, refresh_token = await service.authenticate(
        email=payload.email,
        password=payload.password,
    )
    return _issue_token_response(response, access_token, refresh_token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Renew access token using rotated refresh token",
)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Rotate refresh token and issue fresh access token."""
    if not refresh_token:
        raise AuthenticationError(detail="Missing refresh token cookie")

    service = AuthService(db)
    new_access_token, new_refresh_token = await service.refresh_session(refresh_token)
    return _issue_token_response(response, new_access_token, new_refresh_token)


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


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change authenticated user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Verify current password and persist a new password hash."""
    await RedisRateLimiter().check_endpoint_limit("auth_change_password", _client_ip(request), limit_per_min=5)
    service = AuthService(db)
    await service.change_password(current_user, payload.current_password, payload.new_password)
    return MessageResponse(message="Password updated successfully.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke all sessions and clear authentication cookies",
)
async def logout_all_sessions(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Sign out from all active devices/sessions."""
    service = AuthService(db)
    await service.logout_all_sessions(current_user.id)
    _clear_auth_cookies(response)
    return MessageResponse(message="Signed out of all sessions.")


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


@router.get(
    "/methods",
    response_model=AuthMethodsResponse,
    status_code=status.HTTP_200_OK,
    summary="List enabled passwordless sign-in methods",
)
async def get_auth_methods() -> AuthMethodsResponse:
    """Return whether Google OAuth and Email OTP are configured."""
    return AuthMethodsResponse(
        google_enabled=bool(settings.GOOGLE_CLIENT_ID.strip() and settings.GOOGLE_CLIENT_SECRET.strip()),
        email_otp_enabled=is_smtp_configured(),
    )


def _sign_oauth_state() -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    payload = f"{ts}.{nonce}"
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_oauth_state(state: str | None, max_age_sec: int = 600) -> bool:
    if not state:
        return False
    parts = state.split(".")
    if len(parts) != 3:
        return False
    ts_str, nonce, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > max_age_sec:
        return False
    expected_sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"{ts_str}.{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


@router.get(
    "/google/login",
    summary="Redirect user to Google OAuth 2.0 consent screen",
)
async def google_login() -> RedirectResponse:
    """Initiate Google OAuth 2.0 authorization code flow with signed CSRF state."""
    frontend_login = f"{settings.FRONTEND_URL.rstrip('/')}/login"
    if not settings.GOOGLE_CLIENT_ID.strip() or not settings.GOOGLE_CLIENT_SECRET.strip():
        return RedirectResponse(
            url=f"{frontend_login}?{urlencode({'error': 'Google OAuth is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env.'})}",
            status_code=status.HTTP_302_FOUND,
        )

    state = _sign_oauth_state()
    params = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID.strip(),
        "redirect_uri": settings.GOOGLE_REDIRECT_URI.strip(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/google/callback",
    summary="Handle Google OAuth 2.0 callback and set session cookies",
)
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Exchange Google auth code, verify ID token, and issue VectoCore auth cookies."""
    frontend_base = settings.FRONTEND_URL.rstrip("/")
    frontend_login = f"{frontend_base}/login"

    def _error_redirect(msg: str) -> RedirectResponse:
        return RedirectResponse(url=f"{frontend_login}?{urlencode({'error': msg})}", status_code=status.HTTP_302_FOUND)

    if error:
        return _error_redirect(f"Google sign-in cancelled or failed ({error}).")
    if not code or not _verify_oauth_state(state):
        return _error_redirect("Invalid or expired OAuth state. Please try again.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID.strip(),
                    "client_secret": settings.GOOGLE_CLIENT_SECRET.strip(),
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI.strip(),
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            id_token = token_data.get("id_token")
            if not id_token:
                return _error_redirect("Google did not return an ID token.")

            info_resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
            info_resp.raise_for_status()
            info = info_resp.json()
    except Exception as exc:
        logger.warning("Google OAuth verification failed: %s", exc)
        return _error_redirect("Could not verify Google sign-in. Please try again.")

    if info.get("aud") != settings.GOOGLE_CLIENT_ID.strip():
        return _error_redirect("Google token audience mismatch.")

    email = str(info.get("email", "")).strip().lower()
    google_sub = str(info.get("sub", "")).strip()
    full_name = str(info.get("name") or email.split("@")[0]).strip()
    email_verified = str(info.get("email_verified", "")).lower() == "true"
    if not email or not google_sub or not email_verified:
        return _error_redirect("Your Google account must have a verified email address.")

    service = AuthService(db)
    _, access_token, refresh_token = await service.authenticate_google(
        google_sub=google_sub,
        email=email,
        full_name=full_name,
        email_verified=email_verified,
    )
    redirect_resp = RedirectResponse(url=f"{frontend_base}/", status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(redirect_resp, access_token, refresh_token)
    return redirect_resp


@router.post(
    "/otp/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a 6-digit passwordless OTP to an email address",
)
async def request_email_otp(
    payload: EmailOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Generate and persist OTP immediately, then dispatch SMTP in background for instant UI response."""
    service = AuthService(db)
    norm_email = str(payload.email).strip().lower()
    code = await service.prepare_email_otp(norm_email)
    background_tasks.add_task(send_otp_email, norm_email, code, settings.EMAIL_OTP_EXPIRE_MINUTES, "sign-in")
    return MessageResponse(message="A 6-digit verification code is being sent to your email.")


@router.post(
    "/otp/verify",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify 6-digit email OTP and sign in",
)
async def verify_email_otp(
    payload: EmailOtpVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Verify 6-digit OTP, provision/find user, and set HttpOnly session cookies."""
    service = AuthService(db)
    _, access_token, refresh_token = await service.verify_email_otp(payload.email, payload.code)
    return _issue_token_response(response, access_token, refresh_token)


@router.post(
    "/password-otp/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a 6-digit password reset OTP via email",
)
async def request_password_reset_otp(
    payload: EmailOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Generate a 6-digit reset OTP if the account exists and dispatch SMTP in background."""
    service = AuthService(db)
    norm_email = str(payload.email).strip().lower()
    code = await service.prepare_password_reset_otp(norm_email)
    if code is not None:
        background_tasks.add_task(send_otp_email, norm_email, code, settings.EMAIL_OTP_EXPIRE_MINUTES, "password-reset")
    return MessageResponse(
        message="If an account exists for that email, a 6-digit reset code is on its way."
    )


@router.post(
    "/password-otp/reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using 6-digit email OTP",
)
async def reset_password_via_otp(
    payload: PasswordResetOtpRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Verify 6-digit OTP and set the new password."""
    service = AuthService(db)
    await service.reset_password_with_otp(payload.email, payload.code, payload.new_password)
    return MessageResponse(message="Password reset successfully. You can now sign in.")
