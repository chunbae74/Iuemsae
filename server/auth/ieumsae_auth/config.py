from typing import Literal
from pydantic import Field, field_validator
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")


    database_url: str
    db_password_file: str | None = None

    jwt_private_key_file: str = "../secrets/jwt_p256.pem"
    email_pepper_file: str = "../secrets/email_code_pepper.txt"

    profile_key_file: str = "../secrets/profile_data_key.txt"

    access_ttl_sec: int = Field(default=900, ge=1, le=900)
    refresh_ttl_sec: int = Field(default=2592000, ge=1, le=2592000)
    email_code_ttl_sec: int = Field(default=300, ge=1, le=300)
    email_token_ttl_sec: int = Field(default=600, ge=1, le=600)
    email_code_max_attempts: int = Field(default=5, ge=1, le=5)
    login_max_failures: int = Field(default=5, ge=1, le=10)
    login_lock_sec: int = Field(default=900, ge=1, le=3600)
    device_challenge_ttl_sec: int = Field(default=60, ge=1, le=120)
    max_devices_per_user: int = Field(default=3, ge=1, le=10)


    smtp_host: str
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password_file: str | None = None
    smtp_starttls: Literal[True] = True

    @field_validator("smtp_starttls", mode="before")
    @classmethod
    def require_smtp_tls(cls, value):
        if value is True or (isinstance(value, str) and value.strip().lower() in ("true", "1")):
            return True
        raise ValueError("smtp_starttls_required")
    mail_from: str


    attestation_roots_dir: str = "attestation_roots"
    android_package: str = "kr.ieumsae.app"
    android_signing_cert_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


    integrity_service_account_file: str

    consent_version: str = "2026-10"

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()


settings = Settings()
