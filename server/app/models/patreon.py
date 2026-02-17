from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.license import Base


class PatreonSubscription(Base):
    __tablename__ = "patreon_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patreon_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    patron_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_charge_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow
    )
