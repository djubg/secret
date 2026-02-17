import hashlib
import hmac
import secrets
import uuid

from app.core.settings import get_settings


def generate_access_key() -> str:
    return f"LIC-{uuid.uuid4()}"


def hash_key(access_key: str) -> str:
    settings = get_settings()
    return hashlib.sha256(f"{access_key}{settings.key_pepper}".encode("utf-8")).hexdigest()


def hash_hwid(hwid: str) -> str:
    settings = get_settings()
    return hashlib.sha256(f"{hwid}{settings.hwid_pepper}".encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected = password_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return hmac.compare_digest(digest, expected)


def generate_auth_token() -> str:
    return secrets.token_urlsafe(32)


def hash_auth_token(token: str) -> str:
    settings = get_settings()
    return hashlib.sha256(f"{token}{settings.key_pepper}".encode("utf-8")).hexdigest()


def mask_key(access_key: str) -> str:
    if len(access_key) < 12:
        return "***"
    return f"{access_key[:8]}...{access_key[-6:]}"
