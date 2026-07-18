from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # required secrets
    MQTT_BROKER_HOST: str
    MQTT_ADMIN_USERNAME: str
    MQTT_ADMIN_PASSWORD: str

    # feature toggles
    BACKUP_ENABLED: bool = False
    GRAFANA_LOGGING_ENABLED: bool = False

    # backup — only required when BACKUP_ENABLED=True
    B2_BUCKET_NAME: str = ""
    B2_APPLICATION_KEY_ID: str = ""
    B2_APPLICATION_KEY: str = ""
    B2_ENDPOINT_URL: str = ""
    BACKUP_ENCRYPTION_KEY: str = ""

    # grafana/loki — only required when GRAFANA_LOGGING_ENABLED=True
    LOKI_PUSH_URL: str = ""
    LOKI_USERNAME: str = ""
    LOKI_PASSWORD: str = ""

    # non-secrets with defaults
    ENV: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./db/gateway.db"
    MQTT_BROKER_PORT: int = 8883
    MQTT_CA_CERTS: str = ""
    MQTT_DISCOVERY_PREFIX: str = "homeassistant"
    RATE_LIMIT_READ: str = "60/minute"
    RATE_LIMIT_WRITE: str = "20/minute"
    LOG_LEVEL: str = "INFO"
    MAX_DEVICES_PER_USER: int = 15

    @model_validator(mode="after")
    def _validate_conditional_secrets(self) -> Settings:
        if self.BACKUP_ENABLED:
            missing = [
                name
                for name in (
                    "B2_BUCKET_NAME",
                    "B2_APPLICATION_KEY_ID",
                    "B2_APPLICATION_KEY",
                    "B2_ENDPOINT_URL",
                    "BACKUP_ENCRYPTION_KEY",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"BACKUP_ENABLED is True but missing: {', '.join(missing)}"
                )
        if self.GRAFANA_LOGGING_ENABLED:
            missing = [
                name
                for name in ("LOKI_PUSH_URL", "LOKI_USERNAME", "LOKI_PASSWORD")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"GRAFANA_LOGGING_ENABLED is True but missing: {', '.join(missing)}"
                )
        return self


# pydantic-settings reads env vars at runtime; mypy can't see the kwargs
settings = Settings()  # type: ignore[call-arg]
