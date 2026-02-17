import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LicenseStatus(str, enum.Enum):
    unused = "unused"
    active = "active"
    expired = "expired"
    revoked = "revoked"


class LicenseDuration(str, enum.Enum):
    hour_1 = "1h"
    day_1 = "1d"
    day_30 = "30d"
    lifetime = "lifetime"
    temporary = "temporary"


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    display_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    duration: Mapped[LicenseDuration] = mapped_column(
        Enum(LicenseDuration), default=LicenseDuration.day_30, nullable=False
    )
    status: Mapped[LicenseStatus] = mapped_column(Enum(LicenseStatus), default=LicenseStatus.unused)
    hwid_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    patreon_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    activation_count: Mapped[int] = mapped_column(Integer, default=0)
    temporary_from_patreon: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow
    )
