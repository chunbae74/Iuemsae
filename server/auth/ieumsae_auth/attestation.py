import hmac
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ieumsae_shared.b64 import B64Error, b64d

from .config import settings

KEY_DESCRIPTION_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
SECURITY_LEVELS = {0: "SOFTWARE", 1: "TEE", 2: "STRONGBOX"}
TAG_ATTESTATION_APPLICATION_ID = 709


class AttestationError(Exception):
    pass


@dataclass
class AttestationResult:
    security_level: str
    public_key_b64: str


def _tlv(buf: bytes, pos: int) -> tuple[int, int, int, int]:

    if pos >= len(buf):
        raise AttestationError("DER 길이 오류")
    first = buf[pos]
    cls, num = first >> 6, first & 0x1F
    pos += 1
    if num == 0x1F:
        num = 0
        for _ in range(4):
            if pos >= len(buf):
                raise AttestationError("DER 길이 오류")
            b = buf[pos]
            pos += 1
            num = (num << 7) | (b & 0x7F)
            if not b & 0x80:
                break
        else:
            raise AttestationError("DER 태그 오류")
    if pos >= len(buf):
        raise AttestationError("DER 길이 오류")
    length = buf[pos]
    pos += 1
    if length & 0x80:
        n = length & 0x7F
        if n == 0 or n > 4:
            raise AttestationError("DER 길이 오류")
        length = int.from_bytes(buf[pos : pos + n], "big")
        pos += n
    end = pos + length
    if end > len(buf):
        raise AttestationError("DER 길이 오류")
    return cls, num, pos, end


def _children(buf: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    out, pos = [], start
    while pos < end:
        t = _tlv(buf, pos)
        if t[3] > end or t[3] <= pos:
            raise AttestationError("invalid_der")
        out.append(t)
        pos = t[3]
    return out


def _int(buf: bytes, t) -> int:
    return int.from_bytes(buf[t[2] : t[3]], "big", signed=True)


def parse_key_description(der: bytes) -> dict:
    _, num, s, e = _tlv(der, 0)
    if num != 16:
        raise AttestationError("KeyDescription이 SEQUENCE가 아닙니다")
    f = _children(der, s, e)
    if len(f) < 8:
        raise AttestationError("KeyDescription 필드 부족")
    software = {num: (vs, ve) for (_, num, vs, ve) in _children(der, f[6][2], f[6][3])}
    package = None
    digests = []
    if TAG_ATTESTATION_APPLICATION_ID in software:
        vs, ve = software[TAG_ATTESTATION_APPLICATION_ID]
        try:
            octet = _tlv(der, vs)
            app = _tlv(der, octet[2])
            infos = _children(der, app[2], app[3])
            pkg_set = _children(der, infos[0][2], infos[0][3])
            first_pkg = _children(der, pkg_set[0][2], pkg_set[0][3])
            package = der[first_pkg[0][2] : first_pkg[0][3]].decode("utf-8", "replace")
            digests = [der[t[2]:t[3]].hex() for t in _children(der, infos[1][2], infos[1][3])]
        except (AttestationError, IndexError):
            package = None
    locked = False
    verified = False
    try:
        hardware = {num: (vs, ve) for (_, num, vs, ve) in _children(der, f[7][2], f[7][3])}
        start, end = hardware[704]
        root = _tlv(der, start)
        fields = _children(der, root[2], root[3])
        locked = der[fields[1][2]:fields[1][3]] == b'\xff'
        verified = _int(der, fields[2]) == 0
    except (KeyError, IndexError, AttestationError):
        locked = False
    return {
        "locked": locked,
        "verified": verified,
        "digests": digests,
        "attestation_version": _int(der, f[0]),
        "attestation_security_level": _int(der, f[1]),
        "keymint_security_level": _int(der, f[3]),
        "challenge": der[f[4][2] : f[4][3]],
        "package": package,
    }


def _trusted_roots() -> list[bytes]:
    d = Path(settings.attestation_roots_dir)
    roots = []
    if d.is_dir():
        for p in sorted(d.glob("*.pem")):
            for cert in x509.load_pem_x509_certificates(p.read_bytes()):
                roots.append(
                    cert.public_key().public_bytes(
                        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                    )
                )
    return roots


def verify_attestation(chain_b64: list[str], public_key_b64: str, challenge: bytes) -> AttestationResult:
    if not 2 <= len(chain_b64) <= 8:
        raise AttestationError("인증서 체인 길이 오류")
    try:
        chain = [x509.load_der_x509_certificate(b64d(c, max_len=8192)) for c in chain_b64]
        claimed_spki = b64d(public_key_b64, max_len=512)
    except (B64Error, ValueError) as e:
        raise AttestationError("인증서 형식 오류") from e

    now = datetime.now(timezone.utc)
    if any(now < cert.not_valid_before_utc or now > cert.not_valid_after_utc for cert in chain):
        raise AttestationError("인증서 유효기간이 올바르지 않습니다")
    for index, (child, parent) in enumerate(zip(chain, chain[1:])):
        try:
            constraints = parent.extensions.get_extension_for_class(x509.BasicConstraints).value
            usage = parent.extensions.get_extension_for_class(x509.KeyUsage).value
        except x509.ExtensionNotFound as e:
            raise AttestationError("invalid_ca") from e
        if not constraints.ca or not usage.key_cert_sign:
            raise AttestationError("invalid_ca")
        if constraints.path_length is not None and index > constraints.path_length:
            raise AttestationError("invalid_ca_path")
        try:
            child.verify_directly_issued_by(parent)
        except (InvalidSignature, ValueError, TypeError) as e:
            raise AttestationError("인증서 체인 서명이 맞지 않습니다") from e

    root_spki = chain[-1].public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if root_spki not in _trusted_roots():
        raise AttestationError("구글 증명 루트로 끝나지 않습니다")

    leaf = chain[0]
    leaf_key = leaf.public_key()
    if not isinstance(leaf_key, ec.EllipticCurvePublicKey) or leaf_key.curve.name != "secp256r1":
        raise AttestationError("P-256 키가 아닙니다")
    leaf_spki = leaf_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if not hmac.compare_digest(leaf_spki, claimed_spki):
        raise AttestationError("공개키가 증명 인증서와 다릅니다")

    try:
        ext = leaf.extensions.get_extension_for_oid(KEY_DESCRIPTION_OID)
    except x509.ExtensionNotFound as e:
        raise AttestationError("키 증명 확장이 없습니다") from e
    desc = parse_key_description(ext.value.value)
    if not hmac.compare_digest(desc["challenge"], challenge):
        raise AttestationError("챌린지가 다릅니다")

    level = SECURITY_LEVELS.get(desc["keymint_security_level"], "SOFTWARE")
    if level == "SOFTWARE" or desc["attestation_security_level"] not in (1, 2):
        raise AttestationError("보안 하드웨어에 만든 키가 아닙니다")
    if desc["package"] != settings.android_package:
        raise AttestationError("앱 패키지가 다릅니다")
    if not desc["locked"] or not desc["verified"]:
        raise AttestationError("untrusted_boot")
    if settings.android_signing_cert_sha256.lower() not in desc["digests"]:
        raise AttestationError("untrusted_app_signature")
    return AttestationResult(security_level=level, public_key_b64=public_key_b64)
