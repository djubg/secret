from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="License Backend", alias="APP_NAME")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    database_url: str = Field(default="sqlite:///./license.db", alias="DATABASE_URL")
    admin_token: str = Field(default="change-me-admin-token", alias="ADMIN_TOKEN")
    key_pepper: str = Field(default="change-me-key-pepper", alias="KEY_PEPPER")
    hwid_pepper: str = Field(default="change-me-hwid-pepper", alias="HWID_PEPPER")
    temp_license_hours: int = Field(default=24, alias="TEMP_LICENSE_HOURS")
    patron_active_statuses: str = Field(
        default="active_patron,declined_patron", alias="PATRON_ACTIVE_STATUSES"
    )
    update_base_url: str = Field(
        default="http://127.0.0.1:8000/static/downloads", alias="UPDATE_BASE_URL"
    )
    auth_token_ttl_hours: int = Field(default=720, alias="AUTH_TOKEN_TTL_HOURS")
    avatar_upload_dir: str = Field(default="app/static/avatars", alias="AVATAR_UPLOAD_DIR")
    avatar_max_size_mb: int = Field(default=2, alias="AVATAR_MAX_SIZE_MB")

    @property
    def patron_status_list(self) -> List[str]:
        return [value.strip() for value in self.patron_active_statuses.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
