from typing import Literal
from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STT_", env_file=".env", extra="ignore")

    auth_status_url: HttpUrl
    auth_ca_file: str | None = None

    @field_validator("auth_status_url")
    @classmethod
    def https_status_url(cls, value):
        if value.scheme != "https" or value.username or value.password or value.query or value.fragment:
            raise ValueError("invalid_auth_url")
        return value

    model_path: str = "models/ieumsae_stt.pt"
    device: str = "auto"


    jwt_public_key_file: str = "../secrets/jwt_p256.pub.pem"

    signing_key_file: str = "../secrets/stt_signing_p256.pem"
    signing_key_id: str
    signing_key_not_after: int

    session_ttl_sec: int = Field(default=90, ge=1, le=300)
    max_chunks: int = Field(default=30, ge=1, le=30)
    max_chunk_seconds: Literal[1] = 1
    sample_rate: Literal[16000] = 16000
    max_sessions_per_user: int = Field(default=3, ge=1, le=10)


    tts_provider: str = "elevenlabs"
    elevenlabs_api_key_file: str = "../secrets/elevenlabs_api_key.txt"
    elevenlabs_base_url: Literal["https://api.elevenlabs.io"] = "https://api.elevenlabs.io"

    elevenlabs_model_id: str

    elevenlabs_voice_id: str
    elevenlabs_timeout_sec: float = Field(default=20.0, gt=0, le=30)
    tts_max_chars: int = Field(default=300, ge=1, le=300)


    model_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


settings = Settings()
