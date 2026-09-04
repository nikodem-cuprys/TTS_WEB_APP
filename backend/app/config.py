from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIOBOOK_", env_file=".env")

    data_dir: Path = REPO_ROOT / "data"
    models_dir: Path = REPO_ROOT / "models"

    database_url: str = ""  # filled in from data_dir if left blank

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    tts_workers: int = 4
    max_upload_mb: int = 200

    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def books_dir(self) -> Path:
        return self.data_dir / "books"

    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def output_dir(self) -> Path:
        return self.data_dir / "output"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.books_dir(), self.cache_dir(), self.output_dir(), self.models_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
