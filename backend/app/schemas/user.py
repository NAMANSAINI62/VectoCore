"""Pydantic schemas for user profile data."""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    """Safe public user information schema."""

    id: uuid.UUID
    full_name: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile fields."""

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
