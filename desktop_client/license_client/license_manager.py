from dataclasses import dataclass
from typing import Optional

from desktop_client.license_client.client import LicenseApiClient, LicenseValidation
from desktop_client.utils.crypto.aes_store import SecureKeyStore
from desktop_client.utils.crypto.hmac_signer import HMACSigner
from desktop_client.utils.system_info import build_hwid


@dataclass
class LicenseState:
    is_valid: bool
    key: str
    status: str
    message: str
    expires_at: Optional[str] = None
    seconds_left: Optional[int] = None


class LicenseManager:
    def __init__(
        self,
        api_client: LicenseApiClient,
        key_store: SecureKeyStore,
        signer: HMACSigner,
    ):
        self.api_client = api_client
        self.key_store = key_store
        self.signer = signer
        self.hwid = build_hwid()

    def set_user_token(self, token: str) -> None:
        self.api_client.set_user_token(token)

    def _serialize_signature_payload(self, key: str) -> str:
        return f"{key}|{self.hwid}"

    def save_key(self, key: str) -> None:
        signature = self.signer.sign(self._serialize_signature_payload(key))
        self.key_store.store_json({"key": key, "signature": signature})

    def load_key(self) -> Optional[str]:
        payload = self.key_store.load_json()
        if not payload:
            return None
        key = payload.get("key")
        signature = payload.get("signature", "")
        if not key:
            return None
        if not self.signer.verify(self._serialize_signature_payload(key), signature):
            return None
        return key

    def activate(self, key: str) -> LicenseState:
        result = self.api_client.activate(key, self.hwid)
        if result.get("success"):
            self.save_key(key)
        return LicenseState(
            is_valid=result.get("success", False),
            key=key,
            status=result.get("status", "unknown"),
            message=result.get("message", ""),
            expires_at=result.get("expires_at"),
        )

    def validate_key(self, key: str) -> LicenseState:
        result: LicenseValidation = self.api_client.validate(key, self.hwid)
        if result.valid:
            self.save_key(key)
        return LicenseState(
            is_valid=result.valid,
            key=key,
            status=result.status,
            message=result.message,
            expires_at=result.expires_at,
            seconds_left=result.seconds_left,
        )

    def validate_current(self) -> LicenseState:
        key = self.load_key()
        if not key:
            return LicenseState(
                is_valid=False,
                key="",
                status="missing",
                message="No local license key found.",
            )

        result: LicenseValidation = self.api_client.validate(key, self.hwid)
        return LicenseState(
            is_valid=result.valid,
            key=key,
            status=result.status,
            message=result.message,
            expires_at=result.expires_at,
            seconds_left=result.seconds_left,
        )
