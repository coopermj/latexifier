from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost/latexgen"
    api_keys: str = ""
    storage_path: str = "/data"
    environment: str = "production"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_zip_size: int = 50 * 1024 * 1024  # 50MB

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def api_key_list(self) -> list[str]:
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
