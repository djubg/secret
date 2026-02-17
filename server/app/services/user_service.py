from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.license import LicenseKey, LicenseStatus
from app.models.user import User, UserLicenseLink
from app.services.security import generate_auth_token, hash_auth_token, hash_password, verify_password


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _default_display_name(self, email: str) -> str:
        local = email.split("@", 1)[0]
        return (local or "user")[:64]

    def _issue_token(self, user: User) -> str:
        token = generate_auth_token()
        user.auth_token_hash = hash_auth_token(token)
        user.auth_token_expires_at = datetime.utcnow() + timedelta(hours=self.settings.auth_token_ttl_hours)
        user.last_login_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        return token

    def register(self, email: str, password: str, display_name: Optional[str] = None) -> tuple[User, str]:
        normalized_email = self._normalize_email(email)
        if "@" not in normalized_email or "." not in normalized_email.split("@", 1)[-1]:
            raise ValueError("Invalid email format.")
        existing = self.db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if existing:
            raise ValueError("Email already registered.")

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=(display_name or self._default_display_name(normalized_email)).strip()[:64],
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        token = self._issue_token(user)
        return user, token

    def login(self, email: str, password: str) -> tuple[User, str]:
        normalized_email = self._normalize_email(email)
        if "@" not in normalized_email:
            raise ValueError("Invalid email or password.")
        user = self.db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")
        if not user.is_active:
            raise ValueError("User is disabled.")
        token = self._issue_token(user)
        return user, token

    def get_user_by_token(self, token: str) -> Optional[User]:
        if not token:
            return None
        token_hash = hash_auth_token(token)
        user = self.db.execute(select(User).where(User.auth_token_hash == token_hash)).scalar_one_or_none()
        if not user:
            return None
        if not user.auth_token_expires_at or user.auth_token_expires_at < datetime.utcnow():
            return None
        if not user.is_active:
            return None
        return user

    def update_profile(self, user: User, display_name: Optional[str], avatar_preset: Optional[str]) -> User:
        if display_name is not None and display_name.strip():
            user.display_name = display_name.strip()[:64]
        if avatar_preset is not None:
            user.avatar_preset = avatar_preset.strip()[:64] or None
        self.db.commit()
        self.db.refresh(user)
        return user

    async def save_avatar_upload(self, user: User, upload: UploadFile) -> User:
        if not upload.filename:
            raise ValueError("Missing file name.")
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Unsupported avatar format. Use png, jpg, jpeg, or webp.")

        content = await upload.read()
        max_bytes = self.settings.avatar_max_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"Avatar file too large. Max {self.settings.avatar_max_size_mb} MB.")

        upload_dir = Path(self.settings.avatar_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{user.id}_{uuid.uuid4().hex[:8]}{suffix}"
        target = upload_dir / file_name
        target.write_bytes(content)

        user.avatar_url = f"/static/avatars/{file_name}"
        self.db.commit()
        self.db.refresh(user)
        return user

    def link_license_to_user(self, user_id: str, license_id: str) -> None:
        link = self.db.execute(select(UserLicenseLink).where(UserLicenseLink.license_id == license_id)).scalar_one_or_none()
        if link:
            link.user_id = user_id
        else:
            link = UserLicenseLink(user_id=user_id, license_id=license_id)
            self.db.add(link)
        self.db.commit()

    def list_users(self, limit: int = 300, q: str = "") -> list[User]:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit)
        users = list(self.db.execute(stmt).scalars().all())
        needle = q.strip().lower()
        if not needle:
            return users
        return [
            user
            for user in users
            if needle in user.email.lower() or needle in user.display_name.lower() or needle in user.id.lower()
        ]

    def get_user_licenses(self, user_id: str) -> list[LicenseKey]:
        link_stmt = select(UserLicenseLink).where(UserLicenseLink.user_id == user_id)
        links = list(self.db.execute(link_stmt).scalars().all())
        if not links:
            return []
        license_ids = [item.license_id for item in links]
        stmt = select(LicenseKey).where(LicenseKey.id.in_(license_ids)).order_by(LicenseKey.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

    def build_user_license_summary(self, users: list[User]) -> list[dict]:
        if not users:
            return []
        user_ids = [user.id for user in users]
        links = list(self.db.execute(select(UserLicenseLink).where(UserLicenseLink.user_id.in_(user_ids))).scalars().all())
        license_ids = [link.license_id for link in links]
        licenses = []
        if license_ids:
            licenses = list(self.db.execute(select(LicenseKey).where(LicenseKey.id.in_(license_ids))).scalars().all())
        license_by_id = {item.id: item for item in licenses}
        links_by_user: dict[str, list[UserLicenseLink]] = {}
        for link in links:
            links_by_user.setdefault(link.user_id, []).append(link)

        summary: list[dict] = []
        for user in users:
            user_links = links_by_user.get(user.id, [])
            linked_licenses = [license_by_id[item.license_id] for item in user_links if item.license_id in license_by_id]
            linked_licenses.sort(key=lambda item: item.created_at, reverse=True)
            latest = linked_licenses[0] if linked_licenses else None
            summary.append(
                {
                    "user": user,
                    "license_count": len(linked_licenses),
                    "latest_license_status": latest.status.value if latest else None,
                    "latest_license_key": (latest.full_key or latest.display_key) if latest else None,
                }
            )
        return summary

    def disable_user(self, user_id: str) -> Optional[User]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        user.is_active = False
        user.auth_token_hash = None
        user.auth_token_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user_id: str, revoke_linked_licenses: bool = False) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        links = list(self.db.execute(select(UserLicenseLink).where(UserLicenseLink.user_id == user_id)).scalars().all())
        license_ids = [item.license_id for item in links]
        if revoke_linked_licenses and license_ids:
            licenses = list(self.db.execute(select(LicenseKey).where(LicenseKey.id.in_(license_ids))).scalars().all())
            for license_record in licenses:
                license_record.status = LicenseStatus.revoked
        for link in links:
            self.db.delete(link)
        self.db.delete(user)
        self.db.commit()
        return True

    def get_license_owner_map(self, license_ids: list[str]) -> dict[str, dict]:
        if not license_ids:
            return {}
        links = list(
            self.db.execute(select(UserLicenseLink).where(UserLicenseLink.license_id.in_(license_ids))).scalars().all()
        )
        if not links:
            return {}
        user_ids = list({link.user_id for link in links})
        users = list(self.db.execute(select(User).where(User.id.in_(user_ids))).scalars().all())
        users_by_id = {user.id: user for user in users}
        owner_map: dict[str, dict] = {}
        for link in links:
            user = users_by_id.get(link.user_id)
            if not user:
                continue
            owner_map[link.license_id] = {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "is_active": user.is_active,
            }
        return owner_map
