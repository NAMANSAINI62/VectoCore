"""Pydantic schemas for authentication requests and responses."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Schema for registering a new user."""

    full_name: str = Field(..., min_length=2, max_length=150, description="Full name of user")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="User password (min 8 characters)")


class LoginRequest(BaseModel):
    """Schema for authenticating a user."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    """Schema for authentication and session refresh token responses."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class EmailOtpRequest(BaseModel):
    """Schema for requesting a 6-digit passwordless email OTP."""

    email: EmailStr = Field(..., description="Email address to receive the 6-digit OTP")


class EmailOtpVerifyRequest(BaseModel):
    """Schema for verifying a 6-digit passwordless email OTP."""

    email: EmailStr = Field(..., description="Email address")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit OTP code")


class PasswordResetOtpRequest(BaseModel):
    """Schema for resetting a password using a 6-digit email OTP."""

    email: EmailStr = Field(..., description="Registered email address")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit OTP code")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password (min 8 characters)")


class AuthMethodsResponse(BaseModel):
    """Availability flags for passwordless sign-in methods."""

    google_enabled: bool
    email_otp_enabled: bool


class ChangePasswordRequest(BaseModel):
    """Schema for authenticated password change."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
