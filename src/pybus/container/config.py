from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    DATABASE_TYPE: Literal["sqlalchemy"] = "sqlalchemy"
    DATABASE_URL: str = ""
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
