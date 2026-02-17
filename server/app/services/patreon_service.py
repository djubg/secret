from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.patreon import PatreonSubscription


class PatreonResult:
    def __init__(
        self,
        is_active: bool,
        patreon_user_id: Optional[str],
        patron_status: Optional[str],
        tier_name: Optional[str],
        message: str,
    ):
        self.is_active = is_active
        self.patreon_user_id = patreon_user_id
        self.patron_status = patron_status
        self.tier_name = tier_name
        self.message = message


class PatreonService:
    IDENTITY_URL = (
        "https://www.patreon.com/api/oauth2/v2/identity"
        "?include=memberships.currently_entitled_tiers"
        "&fields[user]=full_name,email"
        "&fields[member]=patron_status,last_charge_status"
        "&fields[tier]=title"
    )

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    async def verify_subscription(self, access_token: str) -> PatreonResult:
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(self.IDENTITY_URL, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return PatreonResult(False, None, None, None, f"Patreon API error: {exc}")

        user = payload.get("data", {})
        relationships = user.get("relationships", {})
        memberships = relationships.get("memberships", {}).get("data", [])
        included = payload.get("included", [])
        tiers = {item.get("id"): item for item in included if item.get("type") == "tier"}
        membership_nodes = {item.get("id"): item for item in included if item.get("type") == "member"}

        patron_status = None
        tier_name = None

        for membership in memberships:
            member_id = membership.get("id")
            member = membership_nodes.get(member_id)
            if not member:
                continue
            attrs = member.get("attributes", {})
            patron_status = attrs.get("patron_status")
            tier_links = member.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
            if tier_links:
                first_tier = tiers.get(tier_links[0].get("id"))
                if first_tier:
                    tier_name = first_tier.get("attributes", {}).get("title")
            break

        patreon_user_id = user.get("id")
        is_active = bool(patreon_user_id and patron_status in self.settings.patron_status_list)
        message = "Patreon subscription active." if is_active else "No active Patreon subscription."
        self._upsert_subscription(patreon_user_id, patron_status, tier_name, is_active)
        return PatreonResult(is_active, patreon_user_id, patron_status, tier_name, message)

    def _upsert_subscription(
        self,
        patreon_user_id: Optional[str],
        patron_status: Optional[str],
        tier_name: Optional[str],
        is_active: bool,
    ) -> None:
        if not patreon_user_id:
            return
        stmt = select(PatreonSubscription).where(PatreonSubscription.patreon_user_id == patreon_user_id)
        existing = self.db.execute(stmt).scalar_one_or_none()
        if not existing:
            existing = PatreonSubscription(
                patreon_user_id=patreon_user_id,
                tier_name=tier_name,
                patron_status=patron_status,
                is_active=is_active,
                last_checked_at=datetime.utcnow(),
            )
            self.db.add(existing)
        else:
            existing.tier_name = tier_name
            existing.patron_status = patron_status
            existing.is_active = is_active
            existing.last_checked_at = datetime.utcnow()
        self.db.commit()
