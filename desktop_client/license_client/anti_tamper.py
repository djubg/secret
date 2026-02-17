import hashlib
import json
import sys
from pathlib import Path


def debugger_detected() -> bool:
    return sys.gettrace() is not None


def verify_checksums(checksum_file: Path, root_dir: Path) -> tuple[bool, str]:
    if not checksum_file.exists():
        return True, "No checksum policy found."

    try:
        checksums = json.loads(checksum_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Checksum file invalid: {exc}"

    for relative_path, expected_hash in checksums.items():
        target = root_dir / relative_path
        if not target.exists():
            return False, f"Missing file: {relative_path}"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected_hash:
            return False, f"Tamper detected in {relative_path}"

    return True, "Checksums verified."
