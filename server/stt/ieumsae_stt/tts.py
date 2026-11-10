import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import httpx

from .config import settings

log = logging.getLogger("ieumsae.tts")


@dataclass(frozen=True)
class Emotion:
    label: str
    tag: str | None
    stability: float
    style: float
    speed: float


EMOTIONS = MappingProxyType({
    "neutral": Emotion("보통", None, 0.6, 0.0, 1.0),
    "happy": Emotion("기쁨", "[happy]", 0.35, 0.5, 1.05),
    "sad": Emotion("슬픔", "[sad]", 0.4, 0.4, 0.9),
    "angry": Emotion("화남", "[angry]", 0.3, 0.6, 1.05),
    "urgent": Emotion("다급함", "[urgent]", 0.3, 0.5, 1.15),
    "gentle": Emotion("부드럽게", "[gently]", 0.5, 0.3, 0.95),
})
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")


class TtsUnavailable(Exception):
    pass


class TtsFailed(Exception):
    pass


def _api_key() -> str | None:
    try:
        key = Path(settings.elevenlabs_api_key_file).read_text(encoding="utf-8").strip()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    return key or None


def _voice_id() -> str:
    voice = settings.elevenlabs_voice_id

    if not VOICE_ID_RE.match(voice):
        raise TtsUnavailable()
    return voice


def provider() -> str:

    if settings.tts_provider == "elevenlabs" and settings.elevenlabs_base_url.startswith("https://") and _api_key():
        return "elevenlabs"
    return "off"


class Synthesizer:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.elevenlabs_base_url,
            timeout=settings.elevenlabs_timeout_sec,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def synthesize(self, text: str, emotion: str) -> tuple[bytes, str]:

        emo = EMOTIONS[emotion]
        if provider() == "off":
            raise TtsUnavailable()
        voice = _voice_id()
        body = {
            "text": f"{emo.tag} {text}" if emo.tag else text,
            "model_id": settings.elevenlabs_model_id,
            "language_code": "ko",
            "voice_settings": {
                "stability": emo.stability,
                "similarity_boost": 0.75,
                "style": emo.style,
                "use_speaker_boost": True,
                "speed": emo.speed,
            },
        }
        try:
            async with asyncio.timeout(30):
                async with self._client.stream(
                    "POST", f"/v1/text-to-speech/{voice}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": _api_key() or "", "Accept": "audio/mpeg"},
                    json=body,
                ) as response:
                    if response.status_code != 200 or response.headers.get("content-type", "").split(";")[0] != "audio/mpeg":
                        raise TtsFailed()
                    audio = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(audio) + len(chunk) > 5 * 1024 * 1024:
                            raise TtsFailed()
                        audio.extend(chunk)
                    if not audio:
                        raise TtsFailed()
                    return bytes(audio), "audio/mpeg"
        except (httpx.HTTPError, TimeoutError):
            log.warning("TTS_FAILED")
            raise TtsFailed() from None
