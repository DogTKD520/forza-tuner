"""
Centralised configuration loaded from environment variables / .env file.

All application code imports from here — nothing reads os.environ directly.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

@lru_cache(maxsize=1)
def _load_tuning_rules() -> dict:
    rules_path = Path(__file__).parent.parent / "config" / "tuning_rules.json"
    with rules_path.open() as file_handle:
        return json.load(file_handle)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # UDP listener
    udp_host: str = "0.0.0.0"
    udp_port: int = 5300

    # Game profile
    default_game: Literal["FM", "FH"] = "FM"

    # Multi-tenancy — MVP default; swap for identity-header value in prod
    default_user_id: str = "local_admin"

    # Database
    database_url: str = "sqlite:///./data/forza_tuner.db"

    # WebSocket throttle
    websocket_fps: int = 15

    # AI / LLM
    use_llm: bool = False
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: int = 120

    @property
    def tuning_rules(self) -> dict:
        """Load tuning thresholds from config/tuning_rules.json (cached per process)."""
        return _load_tuning_rules()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (loaded once at startup)."""
    return Settings()
