import os
from typing import Literal

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class StorageRedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KRULES_STORAGE_REDIS_",
    )

    host: str | None = None
    port: int = 6379
    db: int = 0
    password: str | None = None
    use_tls: bool = False

    key_prefix: str | None = ""

    @computed_field
    @property
    def url(self) -> str | None:
        # Legacy support: check for SUBJECTS_REDIS_URL first
        legacy_url = os.environ.get("SUBJECTS_REDIS_URL")
        if legacy_url:
            return legacy_url

        # Compose URL from individual components
        if self.host is None:
            return None

        protocol = "rediss" if self.use_tls else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"

class KRulesSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KRULES_",
    )

    storage_provider: Literal["empty", "redis"] | None = None
    storage_redis: StorageRedisSettings = StorageRedisSettings()

    @model_validator(mode='after')
    def set_storage_provider_from_redis_config(self) -> 'KRulesSettings':
        if self.storage_provider is None:
            # Check if Redis is configured (either via new settings or legacy SUBJECTS_REDIS_URL)
            if self.storage_redis.url is not None:
                self.storage_provider = "redis"
            else:
                self.storage_provider = "empty"
        return self

