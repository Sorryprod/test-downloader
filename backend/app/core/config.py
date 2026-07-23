from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).resolve().parent


def _ancestor(levels: int) -> Path | None:
    """Вернуть родителя на N уровней выше, либо None если путь короче (как в Docker /app)."""
    try:
        return _CONFIG_DIR.parents[levels]
    except IndexError:
        return None


def _env_files() -> tuple[str, ...]:
    candidates: list[Path] = []
    for levels in (3, 2, 1):
        root = _ancestor(levels)
        if root is not None:
            candidates.append(root / ".env")
    candidates.append(Path.cwd() / ".env")

    existing = tuple(str(path) for path in candidates if path.is_file())
    return existing if existing else (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    external_api_base_url: str = "http://91.199.149.128:18001"
    x_candidate_id: str = "wasireal"

    database_url: str = "postgresql+asyncpg://files:files@localhost:5432/files_db"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost"

    files_storage_dir: str = "./data/files"

    # Пауза между запросами к внешнему API (сек). 0.35 было слишком агрессивно → бан.
    external_api_min_interval_seconds: float = 1.5
    # Доп. запас поверх Retry-After при 429/403
    external_api_retry_buffer_seconds: float = 1.0
    external_api_max_retries: int = 20

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = Path(self.files_storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
