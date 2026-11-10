import time
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pyhpke import AEADId, CipherSuite, KDFId, KEMId, KEMKey

from ieumsae_shared.b64 import b64e


HPKE_SUITE = CipherSuite.new(KEMId.DHKEM_P256_HKDF_SHA256, KDFId.HKDF_SHA256, AEADId.AES256_GCM)
HPKE_ENC_LEN = 65
HPKE_INFO_PREFIX = b"ieumsae-stt-v1|"
TTS_HPKE_INFO_PREFIX = b"ieumsae-tts-v1|"
SESSION_SIG_VERSION = "IEUMSAE-STT-SESSION-V1"
TTS_SESSION_SIG_VERSION = "IEUMSAE-TTS-SESSION-V1"
KEYS_SIG_VERSION = "IEUMSAE-STT-KEYS-V1"


def hpke_info(session_id: str) -> bytes:
    return HPKE_INFO_PREFIX + session_id.encode()


def chunk_aad(session_id: str, seq: int, timestamp: int) -> bytes:
    return f"{session_id}|chunk|{seq}|{timestamp}".encode()


def result_aad(session_id: str) -> bytes:
    return f"{session_id}|result".encode()


def tts_audio_aad(session_id: str) -> bytes:
    return f"{session_id}|tts".encode()


class EphemeralKey:


    def __init__(self) -> None:
        self._sk: ec.EllipticCurvePrivateKey | None = ec.generate_private_key(ec.SECP256R1())
        self.public_raw = self._sk.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )

    def open(self, info: bytes, enc: bytes, ciphertext: bytes) -> bytes:

        if self._sk is None:
            raise ValueError("이미 사용한 키입니다")
        sk, self._sk = self._sk, None
        ctx = HPKE_SUITE.create_recipient_context(enc, KEMKey.from_pyca_cryptography_key(sk), info=info)
        return ctx.open(ciphertext)

    def open_session_key(self, session_id: str, enc: bytes, ciphertext: bytes) -> bytes:
        key = self.open(hpke_info(session_id), enc, ciphertext)
        if len(key) != 32:
            raise ValueError("세션 키 길이 오류")
        return key


def aes_decrypt(key: bytes, iv: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    if len(iv) != 12:
        raise ValueError("IV 길이 오류")
    return AESGCM(key).decrypt(iv, ciphertext, aad)


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    iv = os.urandom(12)
    return iv, AESGCM(key).encrypt(iv, plaintext, aad)


class ServerSigner:
    def __init__(self, pem: bytes, key_id: str, not_after: int):
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
            raise ValueError("STT 서명키는 P-256이어야 합니다")
        self._key = key
        self.key_id = key_id
        self.not_after = not_after
        self.public_spki_b64 = b64e(
            key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        )

    def sign(self, message: bytes) -> str:
        if int(time.time() * 1000) >= self.not_after:
            raise ValueError("signing_key_expired")
        return b64e(self._key.sign(message, ec.ECDSA(hashes.SHA256())))

    def sign_session(
        self,
        *,
        session_id: str,
        hpke_public_b64: str,
        expires_at: int,
        user_id: str,
        device_id: str,
        version: str = SESSION_SIG_VERSION,
    ) -> str:

        msg = "\n".join([version, session_id, hpke_public_b64, self.key_id, str(expires_at), user_id, device_id])
        return self.sign(msg.encode())

    def keys_document(self) -> dict:
        keys = [{"keyId": self.key_id, "publicKey": self.public_spki_b64, "notAfter": self.not_after}]
        body = json.dumps(keys, separators=(",", ":"), sort_keys=True)
        return {"keys": keys, "signature": self.sign(f"{KEYS_SIG_VERSION}\n{body}".encode())}
