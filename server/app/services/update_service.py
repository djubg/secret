import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class UpdateService:
    def __init__(self):
        self.releases_file = Path(__file__).resolve().parent.parent / "static" / "releases.json"

    def _read_payload(self) -> Dict[str, Any]:
        if not self.releases_file.exists():
            return {"latest": {"version": "1.0.0", "download_url": "", "notes": "No release file found."}}
        with self.releases_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            return {"latest": {"version": "1.0.0", "download_url": "", "notes": "Invalid release payload."}}
        return payload

    def _write_payload(self, payload: Dict[str, Any]) -> None:
        self.releases_file.parent.mkdir(parents=True, exist_ok=True)
        with self.releases_file.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    def latest(self) -> Dict[str, Any]:
        payload = self._read_payload()
        latest = payload.get("latest", {})
        if not isinstance(latest, dict):
            return {"version": "1.0.0", "download_url": "", "notes": "Invalid latest release payload."}
        return latest

    def trigger_update_notification(self, message: str | None = None) -> Dict[str, Any]:
        payload = self._read_payload()
        latest = payload.get("latest")
        if not isinstance(latest, dict):
            latest = {"version": "1.0.0", "download_url": "", "notes": ""}
            payload["latest"] = latest

        latest["notice_id"] = datetime.now(timezone.utc).isoformat()
        if message and message.strip():
            latest["notice_message"] = message.strip()
        elif not latest.get("notice_message"):
            latest["notice_message"] = f"Update notification for version {latest.get('version', 'unknown')}."

        self._write_payload(payload)
        return latest
