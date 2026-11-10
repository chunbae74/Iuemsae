import asyncio
import hashlib
import hmac
import json
import logging
from ieumsae_shared.runtime import configure_logging
from ieumsae_shared.web_security import SecurityBoundary
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidTag
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pyhpke import PyHPKEError

from ieumsae_shared.b64 import B64Error, b64d, b64e
from ieumsae_shared.device_sig import NonceCache, SignatureError, verify_request
from ieumsae_shared.tokens import AccessTokenVerifier, TokenError, bearer

from .config import settings
from . import tts
from .authorization import AuthorizationClient
from .crypto import (
    HPKE_ENC_LEN,
    TTS_HPKE_INFO_PREFIX,
    TTS_SESSION_SIG_VERSION,
    ServerSigner,
    aes_decrypt,
    aes_encrypt,
    chunk_aad,
    result_aad,
    tts_audio_aad,
)
from .sessions import SessionStore, SttSession

STT_MODES = ("translate",)

log = logging.getLogger("ieumsae.stt")
configure_logging()

SESSION_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class State:


    def __init__(self) -> None:
        self.recognizer = None
        self.inference_busy = False
        self.verifier: AccessTokenVerifier | None = None
        self.signer: ServerSigner | None = None
        self.sessions: SessionStore | None = None
        self.synth: tts.Synthesizer | None = None
        self.nonces = NonceCache()
        self.authorization = None


state = State()



def _load_recognizer():
    try:
        with Path(settings.model_path).open("rb") as handle:
            blob = handle.read(512 * 1024 * 1024 + 1)
        if len(blob) > 512 * 1024 * 1024:
            log.error("MODEL_INTEGRITY_FAILED")
            return None
    except FileNotFoundError:
        log.error("MODEL_UNAVAILABLE")
        return None
    expected = settings.model_sha256.lower()
    actual = hashlib.sha256(blob).hexdigest()

    if expected is None or not hmac.compare_digest(expected, actual):
        log.error("MODEL_INTEGRITY_FAILED")
        return None
    from .asr.recognizer import Recognizer

    r = Recognizer(blob, settings.device)
    del blob
    r.warmup()
    return r


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.verifier = AccessTokenVerifier(Path(settings.jwt_public_key_file).read_bytes())
    state.signer = ServerSigner(
        Path(settings.signing_key_file).read_bytes(), settings.signing_key_id, settings.signing_key_not_after
    )
    state.sessions = SessionStore(settings.session_ttl_sec, settings.max_sessions_per_user)
    state.recognizer = await asyncio.to_thread(_load_recognizer)
    state.synth = tts.Synthesizer()
    state.authorization = AuthorizationClient()
    log.info("TTS 제공자: %s", tts.provider())
    janitor = asyncio.create_task(state.sessions.janitor())
    try:
        yield
    finally:
        janitor.cancel()
        try:
            await janitor
        except asyncio.CancelledError:
            pass
        try:
            try:
                await state.synth.close()
            finally:
                await state.authorization.close()
        finally:
            state.sessions.wipe_all()


app = FastAPI(title="Ieumsae STT", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_: Request, __: ValidationError):

    return JSONResponse({"error": "invalid_request"}, status_code=422)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return resp


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):

    log.error("REQUEST_FAILED")
    return JSONResponse({"error": "internal_error"}, status_code=500)


class Caller(BaseModel):
    user_id: str
    device_id: str
    tts_consent: bool = False


async def caller(request: Request) -> Caller:
    token = bearer(request.headers.get("authorization"))
    if not token:
        raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = state.verifier.verify(token)
    except TokenError:
        raise HTTPException(401, "invalid_token", headers={"WWW-Authenticate": "Bearer"})

    if not claims.device_id or not claims.device_key:
        raise HTTPException(403, "device_not_registered")

    if request.headers.get("x-device-id") != claims.device_id:
        raise HTTPException(401, "device_mismatch")
    body = await request.body()
    try:
        verify_request(
            device_key_b64=claims.device_key,
            device_id=claims.device_id,
            method=request.method,
            path=request.scope["path"],
            timestamp=request.headers.get("x-timestamp"),
            nonce=request.headers.get("x-nonce"),
            signature=request.headers.get("x-signature"),
            body=body,
            nonces=state.nonces,
        )
    except SignatureError:
        raise HTTPException(401, "invalid_signature")
    consent = await state.authorization.check(token, claims.user_id, claims.device_id)
    return Caller(user_id=claims.user_id, device_id=claims.device_id, tts_consent=consent)


def _session(session_id: str, who: Caller, modes: tuple[str, ...] = STT_MODES) -> SttSession:
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(404, "session_not_found")
    s = state.sessions.get(session_id, who.user_id, who.device_id)

    if s is None or s.mode not in modes:
        raise HTTPException(404, "session_not_found")
    return s


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(Strict):

    mode: Literal["translate"] = "translate"


class SessionKey(Strict):
    enc: str = Field(max_length=100)
    ciphertext: str = Field(max_length=128)


class Chunk(Strict):
    seq: int = Field(ge=0, le=1000)
    timestamp: int = Field(ge=0)
    iv: str = Field(max_length=24)
    ciphertext: str = Field(max_length=64_000)


class Finalize(Strict):
    lastSeq: int = Field(ge=0, le=1000)


@app.get("/system/health")
async def health():
    return {
        "status": "ok",
        "stt": "available" if state.recognizer is not None else "unavailable",
        "tts": "available" if tts.provider() != "off" else "unavailable",
    }


@app.get("/system/keys")
async def keys():
    return state.signer.keys_document()


@app.post("/stt/session")
async def create_session(request: Request, who: Caller = Depends(caller)):
    body = SessionCreate.model_validate_json(await request.body() or b"{}")
    if state.recognizer is None:
        raise HTTPException(503, "stt_unavailable")
    s = state.sessions.create(who.user_id, who.device_id, body.mode)
    hpke_pub = b64e(s.ephemeral.public_raw)
    signature = state.signer.sign_session(
        session_id=s.session_id,
        hpke_public_b64=hpke_pub,
        expires_at=s.expires_at,
        user_id=who.user_id,
        device_id=who.device_id,
    )
    return {
        "sessionId": s.session_id,
        "hpkePublicKey": hpke_pub,
        "serverKeyId": state.signer.key_id,
        "signature": signature,
        "expiresAt": s.expires_at,
        "limits": {
            "sampleRate": settings.sample_rate,
            "maxChunkSeconds": settings.max_chunk_seconds,
            "maxChunks": settings.max_chunks,
        },
    }


@app.post("/stt/session/{session_id}/key", status_code=204)
async def put_key(session_id: str, request: Request, who: Caller = Depends(caller)):
    body = SessionKey.model_validate_json(await request.body())
    s = _session(session_id, who)
    if s.session_key is not None or s.ephemeral is None:
        raise HTTPException(409, "key_already_set")
    try:
        key = s.ephemeral.open_session_key(session_id, b64d(body.enc, max_len=HPKE_ENC_LEN), b64d(body.ciphertext, max_len=64))
    except (B64Error, ValueError, PyHPKEError):

        state.sessions.remove(session_id)
        raise HTTPException(400, "invalid_key")
    s.session_key = bytearray(key)
    return Response(status_code=204)


@app.post("/stt/session/{session_id}/chunk")
async def put_chunk(session_id: str, request: Request, who: Caller = Depends(caller)):
    body = Chunk.model_validate_json(await request.body())
    s = _session(session_id, who)
    if s.session_key is None:
        raise HTTPException(409, "key_not_set")
    if s.finalizing:
        raise HTTPException(409, "session_finalizing")
    if body.seq >= settings.max_chunks:
        raise HTTPException(413, "too_many_chunks")
    if body.seq in s.chunks:
        raise HTTPException(409, "duplicate_chunk")
    if body.timestamp < s.last_timestamp or body.timestamp > s.expires_at:
        raise HTTPException(400, "invalid_timestamp")
    max_bytes = settings.sample_rate * 2 * settings.max_chunk_seconds
    try:
        pcm = aes_decrypt(
            bytes(s.session_key),
            b64d(body.iv, max_len=12),
            b64d(body.ciphertext, max_len=max_bytes + 16),
            chunk_aad(session_id, body.seq, body.timestamp),
        )
    except (B64Error, InvalidTag, ValueError):
        state.sessions.remove(session_id)
        raise HTTPException(400, "invalid_chunk")
    if len(pcm) > max_bytes or len(pcm) % 2:
        state.sessions.remove(session_id)
        raise HTTPException(413, "chunk_too_large")
    s.chunks[body.seq] = bytearray(pcm)
    s.last_timestamp = body.timestamp
    return {"received": body.seq}


@app.post("/stt/session/{session_id}/finalize")
async def finalize(session_id: str, request: Request, who: Caller = Depends(caller)):
    body = Finalize.model_validate_json(await request.body())
    s = _session(session_id, who)
    if s.session_key is None:
        raise HTTPException(409, "key_not_set")
    if s.finalizing:
        raise HTTPException(409, "session_finalizing")
    expected = set(range(body.lastSeq + 1))
    if set(s.chunks) != expected:
        raise HTTPException(409, "missing_chunks")
    if state.inference_busy:
        raise HTTPException(503, "stt_busy")
    state.inference_busy = True
    s.finalizing = True
    audio = bytearray().join(s.chunks[i] for i in range(body.lastSeq + 1))
    key = bytes(s.session_key)
    try:
        started = time.perf_counter()
        task = asyncio.create_task(asyncio.to_thread(state.recognizer.transcribe_pcm16, bytes(audio)))
        try:
            text = await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

        log.info(
            "stt done mode=%s audio=%.1fs chars=%d took=%.0fms",
            s.mode, len(audio) / (settings.sample_rate * 2), len(text), (time.perf_counter() - started) * 1000,
        )
        iv, ct = aes_encrypt(key, json.dumps({"text": text}, ensure_ascii=False).encode(), result_aad(session_id))
        return {"iv": b64e(iv), "ciphertext": b64e(ct)}
    finally:
        state.inference_busy = False
        for i in range(len(audio)):
            audio[i] = 0
        state.sessions.remove(session_id)


@app.delete("/stt/session/{session_id}", status_code=204)
async def cancel(session_id: str, who: Caller = Depends(caller)):
    _session(session_id, who)
    state.sessions.remove(session_id)
    return Response(status_code=204)


class TtsSpeak(Strict):
    enc: str = Field(max_length=100)
    ciphertext: str = Field(max_length=4096)


class TtsPayload(Strict):


    key: str = Field(max_length=64)
    text: str = Field(min_length=1, max_length=300)
    emotion: Literal["neutral", "happy", "sad", "angry", "urgent", "gentle"] = "neutral"


@app.post("/tts/session")
async def create_tts_session(who: Caller = Depends(caller)):
    if not who.tts_consent:

        raise HTTPException(403, "tts_consent_required")
    if tts.provider() == "off":
        raise HTTPException(503, "tts_unavailable")
    s = state.sessions.create(who.user_id, who.device_id, "tts")
    hpke_pub = b64e(s.ephemeral.public_raw)
    signature = state.signer.sign_session(
        session_id=s.session_id,
        hpke_public_b64=hpke_pub,
        expires_at=s.expires_at,
        user_id=who.user_id,
        device_id=who.device_id,
        version=TTS_SESSION_SIG_VERSION,
    )
    return {
        "sessionId": s.session_id,
        "hpkePublicKey": hpke_pub,
        "serverKeyId": state.signer.key_id,
        "signature": signature,
        "expiresAt": s.expires_at,
        "emotions": {k: v.label for k, v in tts.EMOTIONS.items()},
    }


@app.post("/tts/session/{session_id}/speak")
async def tts_speak(session_id: str, request: Request, who: Caller = Depends(caller)):
    if not who.tts_consent:
        raise HTTPException(403, "tts_consent_required")
    body = TtsSpeak.model_validate_json(await request.body())
    s = _session(session_id, who, modes=("tts",))
    try:
        if s.ephemeral is None:
            raise HTTPException(409, "session_used")
        ephemeral = s.ephemeral
        s.ephemeral = None
        try:
            plain = ephemeral.open(
                TTS_HPKE_INFO_PREFIX + session_id.encode(), b64d(body.enc, max_len=HPKE_ENC_LEN), b64d(body.ciphertext, max_len=3072)
            )
            payload = TtsPayload.model_validate_json(plain)
            key = b64d(payload.key, max_len=32)
            if len(key) != 32:
                raise ValueError("키 길이 오류")
        except (B64Error, ValueError, ValidationError, PyHPKEError):
            raise HTTPException(400, "invalid_request")
        text = payload.text.strip()
        if not text or len(text) > settings.tts_max_chars:
            raise HTTPException(400, "invalid_text")
        started = time.perf_counter()
        try:
            audio, mime = await state.synth.synthesize(text, payload.emotion)
        except tts.TtsUnavailable:
            raise HTTPException(503, "tts_unavailable")
        except tts.TtsFailed:
            raise HTTPException(502, "tts_failed")

        log.info(
            "tts done emotion=%s chars=%d bytes=%d took=%.0fms",
            payload.emotion, len(text), len(audio), (time.perf_counter() - started) * 1000,
        )
        iv, ct = aes_encrypt(key, audio, tts_audio_aad(session_id))
        return {"iv": b64e(iv), "ciphertext": b64e(ct), "mimeType": mime}
    finally:
        state.sessions.remove(session_id)


app.add_middleware(SecurityBoundary)
