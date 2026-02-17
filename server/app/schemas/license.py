from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerateKeyRequest(BaseModel):
    duration: Literal["1h", "1d", "30d", "lifetime"] = Field(default="30d")
    patreon_user_id: Optional[str] = None
    notes: Optional[str] = None


class GenerateKeyResponse(BaseModel):
    key: str
    duration: str
    expires_at: Optional[datetime]
    status: str


class ActivateRequest(BaseModel):
    key: str = Field(min_length=8, max_length=128, examples=["LIC-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"])
    hwid: str = Field(min_length=4, max_length=256, examples=["PC-ABC123"])


class ActivateResponse(BaseModel):
    success: bool
    message: str
    status: str
    expires_at: Optional[datetime]


class ValidateResponse(BaseModel):
    valid: bool
    status: str
    expires_at: Optional[datetime]
    message: str
    seconds_left: Optional[int] = None
    temporary_license: bool = False


class PatreonAuthResponse(BaseModel):
    patreon_active: bool
    patreon_user_id: Optional[str]
    generated_key: Optional[str] = None
    expires_at: Optional[datetime] = None
    message: str


class ValidateRequest(BaseModel):
    key: str = Field(min_length=8, max_length=128)
    hwid: str = Field(min_length=4, max_length=256)


class ExtendLicenseRequest(BaseModel):
    add: Literal["1h", "1d", "7d", "30d"] = "1d"


class HubActionResponse(BaseModel):
    success: bool
    message: str
    status: Optional[str] = None


class LicenseDashboardItem(BaseModel):
    display_key: str
    duration: str
    status: str
    expires_at: Optional[datetime]
    hwid_bound: bool
    patreon_user_id: Optional[str]
    created_at: datetime
