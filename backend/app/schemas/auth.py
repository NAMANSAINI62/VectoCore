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
    """Schema for authentication token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshResponse(BaseModel):
    """Schema returned on token refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    """Schema for initiating password recovery."""

    email: EmailStr = Field(..., description="Registered email address")


class ResetPasswordRequest(BaseModel):
    """Schema for resetting password with token."""

    token: str = Field(..., min_length=10, description="Password recovery token")
    new_password: str = Field(..., min_length=8, max_length=128, description="New secure password")


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
