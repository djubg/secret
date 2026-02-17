from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


@dataclass
class LicenseValidation:
    valid: bool
    status: str
    message: str
    expires_at: Optional[str]
    seconds_left: Optional[int]
    temporary_license: bool


class LicenseApiClient:
    def __init__(self, base_url: str, timeout: int = 12):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_token = ""

    def set_user_token(self, token: str) -> None:
        self.user_token = token.strip()

    def _auth_headers(self) -> dict:
        if not self.user_token:
            return {}
        return {"X-User-Token": self.user_token}

    def activate(self, key: str, hwid: str) -> dict:
        response = requests.post(
            f"{self.base_url}/activate",
            json={"key": key, "hwid": hwid},
            headers=self._auth_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def validate(self, key: str, hwid: str) -> LicenseValidation:
        response = requests.get(
            f"{self.base_url}/validate",
            params={"key": key, "hwid": hwid},
            headers=self._auth_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return LicenseValidation(
            valid=data.get("valid", False),
            status=data.get("status", "unknown"),
            message=data.get("message", ""),
            expires_at=data.get("expires_at"),
            seconds_left=data.get("seconds_left"),
            temporary_license=data.get("temporary_license", False),
        )

    def register(self, email: str, password: str, display_name: str) -> dict:
        response = requests.post(
            f"{self.base_url}/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        self.set_user_token(data.get("token", ""))
        return data

    def login(self, email: str, password: str) -> dict:
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        self.set_user_token(data.get("token", ""))
        return data

    def me(self) -> dict:
        response = requests.get(
            f"{self.base_url}/me",
            headers=self._auth_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_profile(self, display_name: str | None = None, avatar_preset: str | None = None) -> dict:
        payload = {}
        if display_name is not None:
            payload["display_name"] = display_name
        if avatar_preset is not None:
            payload["avatar_preset"] = avatar_preset
        response = requests.patch(
            f"{self.base_url}/me/profile",
            json=payload,
            headers=self._auth_headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def upload_avatar(self, file_path: str) -> dict:
        path = Path(file_path)
        with path.open("rb") as stream:
            files = {"file": (path.name, stream, "application/octet-stream")}
            response = requests.post(
                f"{self.base_url}/me/avatar",
                files=files,
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()
