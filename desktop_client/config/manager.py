import json
from pathlib import Path

from desktop_client.config.defaults import AppSettings


class ConfigManager:
    _LOCKED_FIELDS = {"api_base_url"}

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = self._load()

    def _load(self) -> AppSettings:
        if not self.config_path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        with self.config_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        defaults = AppSettings().to_dict()
        for key, value in payload.items():
            if key in defaults and key not in self._LOCKED_FIELDS:
                defaults[key] = value
        return AppSettings(**defaults)

    def save(self, settings: AppSettings | None = None) -> None:
        to_save = settings or self.settings
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(to_save.to_dict(), file, indent=2)

    def reset(self) -> AppSettings:
        self.settings = AppSettings()
        self.save(self.settings)
        return self.settings
