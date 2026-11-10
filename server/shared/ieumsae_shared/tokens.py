import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key


JWT_ALG = "ES256"
ISSUER = "ieumsae-auth"
AUDIENCE = "ieumsae"


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    jti: str
    issued_at: int
    session_id: str | None
    password_version: int | None
    device_id: str | None
    device_key: str | None
    tts_consent: bool = False


class AccessTokenVerifier:
    def __init__(self, public_key_pem: bytes):
        self._key = load_pem_public_key(public_key_pem)

    def verify(self, token: str) -> AccessClaims:
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=[JWT_ALG],
                audience=AUDIENCE,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub", "jti", "typ"]},
                leeway=5,
            )
        except jwt.PyJWTError as e:
            raise TokenError("유효하지 않은 토큰") from e
        try:
            uuid.UUID(claims["sub"])
            uuid.UUID(claims["sid"])
            if not isinstance(claims.get("pwv"), int):
                raise ValueError()
            cnf = claims.get("cnf") or {}
            if not isinstance(cnf, dict):
                raise ValueError()
            if cnf:
                uuid.UUID(cnf["did"])
                if not isinstance(cnf.get("dkey"), str):
                    raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise TokenError("invalid_claims") from None
        if claims.get("typ") != "access":
            raise TokenError("액세스 토큰이 아닙니다")
        cnf = claims.get("cnf") or {}
        return AccessClaims(
            user_id=str(claims["sub"]),
            jti=str(claims["jti"]),
            issued_at=int(claims["iat"]),
            session_id=claims.get("sid"),
            password_version=claims.get("pwv"),
            device_id=cnf.get("did"),
            device_key=cnf.get("dkey"),
            tts_consent=claims.get("tts") is True,
        )


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()
