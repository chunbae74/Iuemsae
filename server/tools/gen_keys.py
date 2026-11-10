import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import os
import sys
import re
import secrets
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from host_secrets import SecretStore
SECRETS = ROOT / "server" / "secrets"
ANDROID_RES = ROOT / "android" / "app" / "src" / "debug" / "res" / "raw"
ANDROID_CFG = ROOT / "android" / "server-keys.properties"


def write(path: Path, data: bytes, force: bool) -> bool:
    if path.is_symlink():
        raise ValueError("invalid_output")
    path.parent.mkdir(parents=True, exist_ok=True)

    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    return True


def pem_private(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def pem_public(key) -> bytes:
    return key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def make_tls(hosts: list[str], force: bool, store: SecretStore) -> None:
    tls = SECRETS / "tls"
    if (tls / "server.pem").exists() and not force:
        if "tls/server.key" not in store.load():
            raise ValueError("TLS_KEY_REQUIRED")
        return
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ieumsae Dev CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    srv_key = ec.generate_private_key(ec.SECP256R1())
    sans: list[x509.GeneralName] = []
    for h in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    srv = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    write(tls / "ca.pem", ca.public_bytes(serialization.Encoding.PEM), True)
    store.put("tls/server.key", pem_private(srv_key), force=True)
    write(tls / "server.pem", srv.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM), True)


def spki_pin(cert_pem: bytes) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem)
    spki = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "sha256/" + base64.b64encode(hashlib.sha256(spki).digest()).decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--host", action="append", default=[], help="TLS 인증서에 넣을 호스트/IP (여러 번 가능)")
    ap.add_argument("--signing-key-id", required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.signing_key_id):
        ap.error("invalid signing key id")
    if not args.host:
        ap.error("--host is required")


    store = SecretStore(SECRETS)
    store.require_migrated()
    jwt_key = ec.generate_private_key(ec.SECP256R1())
    if store.put("jwt_p256.pem", pem_private(jwt_key), args.force):
        write(SECRETS / "jwt_p256.pub.pem", pem_public(jwt_key.public_key()), True)

    stt_key = ec.generate_private_key(ec.SECP256R1())
    if store.put("stt_signing_p256.pem", pem_private(stt_key), args.force):
        write(SECRETS / "stt_signing_p256.pub.pem", pem_public(stt_key.public_key()), True)

    store.put("email_code_pepper.txt", secrets.token_urlsafe(32).encode(), args.force)
    store.put("db_password.txt", secrets.token_urlsafe(24).encode(), args.force)

    store.put("profile_data_key.txt", base64.b64encode(secrets.token_bytes(32)), args.force)

    store.put("elevenlabs_api_key.txt", b"", False)

    hosts = args.host
    make_tls(hosts, args.force, store)


    stt_pub = serialization.load_pem_public_key((SECRETS / "stt_signing_p256.pub.pem").read_bytes())
    stt_spki = base64.b64encode(
        stt_pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    ).decode()

    tls_pin = spki_pin((SECRETS / "tls" / "ca.pem").read_bytes())
    ANDROID_CFG.parent.mkdir(parents=True, exist_ok=True)
    ANDROID_CFG.write_text(
        f"sttSigningKeyId={args.signing_key_id}\nsttSigningPublicKey={stt_spki}\ntlsPin={tls_pin}\n",
        encoding="utf-8",
    )
    write(ANDROID_RES / "dev_ca.pem", (SECRETS / "tls" / "ca.pem").read_bytes(), True)


def run() -> int:
    try:
        main()
    except OSError:
        print("KEY_GENERATION_FAILED", file=sys.stderr)
        return 1
    except (ValueError, TypeError, UnsupportedAlgorithm):
        print("KEY_GENERATION_FAILED", file=sys.stderr)
        return 1
    except Exception:
        # Do not disclose generated material on unexpected library failures.
        print("KEY_GENERATION_FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
