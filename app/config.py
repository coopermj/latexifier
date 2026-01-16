from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_keys: str = ""
    storage_path: str = "/data"
    environment: str = "production"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_zip_size: int = 50 * 1024 * 1024  # 50MB
    esv_api_key: str = ""
    anthropic_api_key: str = ""
    web_password: str = ""
    pdf_retention_days: int = 8

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def api_key_list(self) -> list[str]:
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
