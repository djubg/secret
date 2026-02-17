import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from desktop_client.config.version import APP_VERSION


def _version_tuple(value: str) -> tuple:
    return tuple(int(part) for part in value.split("."))


class UpdaterClient:
    def __init__(self, api_base_url: str, timeout: int = 20):
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout

    def check(self) -> dict:
        response = requests.get(f"{self.api_base_url}/updates/latest", timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        latest = payload.get("version", APP_VERSION)
        payload["is_newer"] = _version_tuple(latest) > _version_tuple(APP_VERSION)
        return payload

    def download(
        self,
        url: str,
        target_zip: Path,
        progress_cb: Optional[Callable[[int], None]] = None,
    ) -> Path:
        target_zip.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with target_zip.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 32):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_cb:
                        progress_cb(int(downloaded * 100 / total))
        return target_zip

    def extract_package(self, zip_path: Path, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(destination)
        return destination

    def cleanup_old(self, updates_dir: Path, keep: int = 3) -> None:
        if not updates_dir.exists():
            return
        items = sorted([p for p in updates_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
        for item in items[keep:]:
            shutil.rmtree(item, ignore_errors=True)
