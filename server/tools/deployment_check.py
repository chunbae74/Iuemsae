import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host_secrets import PRIVATE_FILES, SecretStore


def check():
    configuration = {}
    environment = ROOT / '.env'
    if environment.is_file():
        for line in environment.read_text(encoding='utf-8').splitlines():
            key, separator, value = line.partition('=')
            if separator:
                configuration[key.strip()] = value.strip().strip('"').strip("'")
    configuration.update(os.environ)
    required = (
        'AUTH_SMTP_HOST', 'AUTH_SMTP_USER', 'AUTH_MAIL_FROM',
        'AUTH_ANDROID_SIGNING_CERT_SHA256', 'ELEVENLABS_MODEL_ID',
        'ELEVENLABS_VOICE_ID', 'STT_SIGNING_KEY_ID', 'STT_SIGNING_KEY_NOT_AFTER',
        'STT_MODEL_SHA256', 'STT_AUTH_STATUS_URL', 'TRUSTED_PROXY_IPS',
    )
    results = {key: bool(configuration.get(key)) for key in required}
    store = SecretStore(ROOT / 'secrets')
    store.require_migrated()
    private = store.load()
    for filename in ('smtp_password.txt', 'integrity_service_account.json', 'elevenlabs_api_key.txt',
                     'db_password.txt', 'jwt_p256.pem', 'jwt_p256.pub.pem',
                     'stt_signing_p256.pem', 'profile_data_key.txt', 'email_code_pepper.txt'):
        path = ROOT / 'secrets' / filename
        results[filename] = bool(private.get(filename)) if filename in PRIVATE_FILES else path.is_file() and path.stat().st_size > 0
    try:
        data = json.loads(private.get('integrity_service_account.json', b'{}'))
        results['integrity_account_format'] = data.get('type') == 'service_account' and bool(data.get('client_email')) and bool(data.get('private_key'))
    except (OSError, ValueError, TypeError):
        results['integrity_account_format'] = False
    try:
        cert = x509.load_pem_x509_certificate((ROOT / 'secrets/tls/server.pem').read_bytes())
        key = serialization.load_pem_private_key(private.get('tls/server.key', b''), None)
        encoding = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        now = datetime.now(timezone.utc)
        results['tls_certificate'] = (
            cert.not_valid_before_utc <= now < cert.not_valid_after_utc
            and cert.public_key().public_bytes(*encoding) == key.public_key().public_bytes(*encoding)
            and 'Dev CA' not in cert.issuer.rfc4514_string()
            and cert.issuer != cert.subject
        )
    except (OSError, ValueError, TypeError):
        results['tls_certificate'] = False
    try:
        with (ROOT / 'stt/models/ieumsae_stt.pt').open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        results['model_integrity'] = hmac.compare_digest(digest, configuration.get('STT_MODEL_SHA256', '').lower())
    except OSError:
        results['model_integrity'] = False
    results['attestation_roots'] = (ROOT / 'auth/attestation_roots/google-hardware-roots.pem').is_file()
    executable = shutil.which('docker')
    results['container_engine'] = False
    if executable:
        try:
            result = subprocess.run([executable, 'info', '--format', '{{.ServerVersion}}'],
                                    capture_output=True, timeout=15, check=False)
            results['container_engine'] = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            results['container_engine'] = False
    print(json.dumps({'ready': all(results.values()), 'checks': results}, sort_keys=True))
    return 0 if all(results.values()) else 1


def main():
    try:
        return check()
    except OSError:
        print('{"ready":false,"error":"deployment_check_failed"}')
        return 1
    except (ValueError, TypeError, KeyError, AttributeError):
        print('{"ready":false,"error":"deployment_check_failed"}')
        return 1
    except Exception:
        # Keep unexpected provider/parser failures out of public diagnostics.
        print('{"ready":false,"error":"deployment_check_failed"}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
