"""
SQLModel / SQLite async engine setup.

Tables are created automatically at startup so there is no separate migration
step required for the MVP. The database file location is driven entirely by
the DATABASE_URL setting so it is never hardcoded here.
"""

from pathlib import Path

from sqlmodel import SQLModel, create_engine, Session

from app.config import get_settings

settings = get_settings()

# Ensure the data directory exists before SQLite tries to open the file
_db_path = settings.database_url.replace("sqlite:///", "")
Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

# connect_check_same_thread=False is required for FastAPI's thread-pool workers
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """Create all SQLModel tables (idempotent — safe to call multiple times)."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a database session and closes it after use."""
    with Session(engine) as session:
        yield session
