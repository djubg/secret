from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=6, max_length=128)
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: Optional[str]
    avatar_preset: Optional[str]
    created_at: datetime
    last_login_at: Optional[datetime]


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=64)
    avatar_preset: Optional[str] = Field(default=None, min_length=1, max_length=64)


class AdminUserSummary(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: Optional[str]
    license_count: int
    latest_license_status: Optional[str]
    latest_license_key: Optional[str]
    created_at: datetime


class AdminUserDetail(BaseModel):
    user: UserResponse
    licenses: list[dict]
