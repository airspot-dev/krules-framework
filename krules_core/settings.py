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

    key_prefix: str | None = ""

    @computed_field
    @property
    def url(self) -> str | None:
        if self.host is None:
            return None
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"

class KRulesSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KRULES_",
    )

    storage_provider: Literal["empty", "redis"] | None = None
    storage_redis: StorageRedisSettings = StorageRedisSettings()

    @model_validator(mode='after')
    def set_storage_provider_from_redis_config(self) -> 'KRulesSettings':
        if self.storage_provider is None:
            if self.storage_redis.host is not None:
                self.storage_provider = "redis"
            else:
                self.storage_provider = "empty"
        return self

