from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.license import LicenseDuration, LicenseKey, LicenseStatus
from app.models.user import UserLicenseLink
from app.services.security import generate_access_key, hash_hwid, hash_key, mask_key


class LicenseService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_expiration(self, duration: LicenseDuration) -> Optional[datetime]:
        now = datetime.utcnow()
        if duration == LicenseDuration.hour_1:
            return now + timedelta(hours=1)
        if duration == LicenseDuration.day_1:
            return now + timedelta(days=1)
        if duration == LicenseDuration.day_30:
            return now + timedelta(days=30)
        if duration == LicenseDuration.temporary:
            settings = get_settings()
            return now + timedelta(hours=settings.temp_license_hours)
        return None

    def _normalize_duration(self, duration: str) -> LicenseDuration:
        mapping = {
            "1h": LicenseDuration.hour_1,
            "1d": LicenseDuration.day_1,
            "30d": LicenseDuration.day_30,
            "lifetime": LicenseDuration.lifetime,
            "temporary": LicenseDuration.temporary,
        }
        if duration not in mapping:
            raise ValueError("Unsupported duration. Use 1h, 1d, 30d or lifetime.")
        return mapping[duration]

    def generate_key(
        self,
        duration_value: str,
        patreon_user_id: Optional[str] = None,
        notes: Optional[str] = None,
        temporary: bool = False,
    ) -> tuple[str, LicenseKey]:
        duration = self._normalize_duration("temporary" if temporary else duration_value)
        raw_key = generate_access_key()
        model = LicenseKey(
            key_hash=hash_key(raw_key),
            full_key=raw_key,
            display_key=mask_key(raw_key),
            duration=duration,
            expires_at=self._resolve_expiration(duration),
            status=LicenseStatus.unused,
            patreon_user_id=patreon_user_id,
            temporary_from_patreon=temporary,
            notes=notes,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return raw_key, model

    def _fetch_by_key(self, access_key: str) -> Optional[LicenseKey]:
        stmt = select(LicenseKey).where(LicenseKey.key_hash == hash_key(access_key))
        return self.db.execute(stmt).scalar_one_or_none()

    def _is_expired(self, record: LicenseKey) -> bool:
        return bool(record.expires_at and datetime.utcnow() > record.expires_at)

    def activate_key(self, access_key: str, hwid: str) -> tuple[bool, str, Optional[LicenseKey]]:
        record = self._fetch_by_key(access_key)
        if not record:
            return False, "Invalid access key.", None

        if record.status == LicenseStatus.revoked:
            return False, "License revoked.", record

        if self._is_expired(record):
            record.status = LicenseStatus.expired
            self.db.commit()
            return False, "License expired.", record

        requested_hwid_hash = hash_hwid(hwid)
        if record.status == LicenseStatus.unused:
            record.hwid_hash = requested_hwid_hash
            record.activated_at = datetime.utcnow()
            record.last_validated_at = datetime.utcnow()
            record.activation_count += 1
            record.status = LicenseStatus.active
            self.db.commit()
            self.db.refresh(record)
            return True, "License activated.", record

        if record.hwid_hash != requested_hwid_hash:
            return False, "License already bound to another machine.", record

        record.last_validated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return True, "License already active on this machine.", record

    def validate_key(self, access_key: str, hwid: str) -> tuple[bool, str, Optional[LicenseKey], Optional[int]]:
        record = self._fetch_by_key(access_key)
        if not record:
            return False, "Invalid access key.", None, None

        if record.status == LicenseStatus.revoked:
            return False, "License revoked.", record, None

        if self._is_expired(record):
            record.status = LicenseStatus.expired
            self.db.commit()
            return False, "License expired.", record, 0

        if record.hwid_hash and record.hwid_hash != hash_hwid(hwid):
            return False, "License bound to a different machine.", record, None

        if record.status == LicenseStatus.unused:
            return False, "License not activated.", record, None

        seconds_left = None
        if record.expires_at:
            seconds_left = max(0, int((record.expires_at - datetime.utcnow()).total_seconds()))

        record.last_validated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return True, "License valid.", record, seconds_left

    def list_licenses(self, limit: int = 200) -> list[LicenseKey]:
        stmt = select(LicenseKey).order_by(LicenseKey.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def get_license_by_id(self, license_id: str) -> Optional[LicenseKey]:
        stmt = select(LicenseKey).where(LicenseKey.id == license_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def extend_license(self, license_id: str, add_value: str) -> Optional[LicenseKey]:
        record = self.get_license_by_id(license_id)
        if not record:
            return None

        now = datetime.utcnow()
        mapping = {
            "1h": timedelta(hours=1),
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        delta = mapping.get(add_value)
        if delta is None:
            raise ValueError("Unsupported extension value. Use 1h, 1d, 7d or 30d.")

        if record.duration == LicenseDuration.lifetime and record.expires_at is None:
            return record

        base = record.expires_at if record.expires_at and record.expires_at > now else now
        record.expires_at = base + delta
        if record.status in (LicenseStatus.expired, LicenseStatus.revoked):
            record.status = LicenseStatus.active if record.hwid_hash else LicenseStatus.unused
        self.db.commit()
        self.db.refresh(record)
        return record

    def revoke_license(self, license_id: str) -> Optional[LicenseKey]:
        record = self.get_license_by_id(license_id)
        if not record:
            return None
        record.status = LicenseStatus.revoked
        self.db.commit()
        self.db.refresh(record)
        return record

    def reactivate_license(self, license_id: str) -> Optional[LicenseKey]:
        record = self.get_license_by_id(license_id)
        if not record:
            return None
        record.status = LicenseStatus.active if record.hwid_hash else LicenseStatus.unused
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete_license(self, license_id: str) -> bool:
        record = self.get_license_by_id(license_id)
        if not record:
            return False
        link = self.db.execute(select(UserLicenseLink).where(UserLicenseLink.license_id == license_id)).scalar_one_or_none()
        if link:
            self.db.delete(link)
        self.db.delete(record)
        self.db.commit()
        return True
