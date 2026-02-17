from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import get_settings

settings = get_settings()


def _resolve_database_url(raw_url: str) -> str:
    if not raw_url.startswith("sqlite:///"):
        return raw_url

    sqlite_path = raw_url.replace("sqlite:///", "", 1)
    if sqlite_path == ":memory:":
        return raw_url

    is_windows_abs = len(sqlite_path) > 1 and sqlite_path[1] == ":"
    is_unix_abs = sqlite_path.startswith("/")
    if is_windows_abs or is_unix_abs:
        return raw_url

    sqlite_path = sqlite_path[2:] if sqlite_path.startswith("./") else sqlite_path
    base_dir = Path(__file__).resolve().parents[2]  # server/
    absolute_path = (base_dir / sqlite_path).resolve()
    return f"sqlite:///{absolute_path.as_posix()}"


resolved_database_url = _resolve_database_url(settings.database_url)

engine = create_engine(
    resolved_database_url,
    connect_args={"check_same_thread": False} if resolved_database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
