import asyncio
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for directory in ("shared", "auth"):
    sys.path.insert(0, str(ROOT / directory))


class AuthenticationSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        key = ec.generate_private_key(ec.SECP256R1())
        (root / "jwt.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (root / "pepper").write_text(secrets.token_hex(32))
        import base64
        (root / "profile").write_text(base64.b64encode(secrets.token_bytes(32)).decode())
        cls.environment = patch.dict(os.environ, {
            "AUTH_ANDROID_SIGNING_CERT_SHA256": "0" * 64,
            "AUTH_DATABASE_URL": f"sqlite+aiosqlite:///{(root / 'test.db').as_posix()}",
            "AUTH_JWT_PRIVATE_KEY_FILE": str(root / "jwt.pem"),
            "AUTH_EMAIL_PEPPER_FILE": str(root / "pepper"),
            "AUTH_PROFILE_KEY_FILE": str(root / "profile"),
            "AUTH_SMTP_HOST": "smtp.example.invalid",
            "AUTH_MAIL_FROM": "test@example.invalid",
            "AUTH_INTEGRITY_SERVICE_ACCOUNT_FILE": str(root / "absent.json"),
        })
        cls.environment.start()
        from ieumsae_auth.main import app
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.environment.stop()
        cls.temp.cleanup()

    def test_authentication_requires_issued_code_and_valid_password(self):
        from ieumsae_auth import mailer
        email = f"{secrets.token_hex(5)}@example.com"
        login = "u" + secrets.token_hex(5)
        password = secrets.token_hex(12) + "Az!"
        self.assertEqual(self.client.post("/auth/email/verify", json={"email": email, "code": f"{secrets.randbelow(1000000):06d}"}).status_code, 400)
        with patch.object(mailer, "send", new_callable=AsyncMock) as send:
            self.assertEqual(self.client.post("/auth/email/code", json={"email": email}).status_code, 202)
            import re
            code = re.search(r"\b\d{6}\b", send.call_args.args[2]).group()
        verified = self.client.post("/auth/email/verify", json={"email": email, "code": code})
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(self.client.post("/auth/email/verify", json={"email": email, "code": code}).status_code, 400)
        signup = {"loginId": login, "password": "x", "emailToken": verified.json()["emailToken"], "consents": {"terms": True, "privacy": True, "sensitiveVoice": True}}
        self.assertEqual(self.client.post("/auth/signup", json=signup).status_code, 400)
        signup["password"] = password
        self.assertEqual(self.client.post("/auth/signup", json=signup).status_code, 201)
        self.assertEqual(self.client.post("/auth/login", json={"loginId": login, "password": secrets.token_hex(12)}).status_code, 401)
        logged = self.client.post("/auth/login", json={"loginId": login, "password": password})
        self.assertEqual(logged.status_code, 200)
        headers = {"Authorization": "Bearer " + logged.json()["accessToken"]}
        self.assertEqual(self.client.put("/user/communication", headers=headers, json={"comprehensionLevel": 2, "consent": False}).status_code, 400)
        self.assertEqual(self.client.put("/user/communication", headers=headers, json={"comprehensionLevel": 2, "consent": True}).status_code, 204)
        self.assertEqual(self.client.get("/user/profile", headers=headers).json()["communication"]["comprehensionLevel"], 2)
        self.assertEqual(self.client.put("/auth/password", headers=headers, json={"currentPassword": password, "newPassword": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/auth/logout", json={"refreshToken": logged.json()["refreshToken"]}).status_code, 204)
        self.assertEqual(self.client.get("/user/profile", headers=headers).status_code, 401)
        self.assertEqual(self.client.post("/auth/refresh", json={"refreshToken": logged.json()["refreshToken"]}).status_code, 401)

    def test_device_removal_revokes_access_and_refresh(self):
        import uuid
        from ieumsae_auth.db import SessionLocal
        from ieumsae_auth.models import User, Device
        from ieumsae_auth.security import hash_password
        from ieumsae_auth import sessions, profile

        async def seed():
            async with SessionLocal() as db:
                user = User(login_id="u" + secrets.token_hex(5), email=secrets.token_hex(5) + "@example.com",
                            password_hash=hash_password(secrets.token_hex(24)), password_changed_at=sessions.now())
                db.add(user)
                await db.flush()
                device = Device(user_id=user.id, public_key="test-public-key", security_level="TEE", sdk_int=35)
                db.add(device)
                await db.flush()
                await profile.record_consent(db, user.id, tts_overseas=True)
                await db.flush()
                tokens = await sessions.start(db, user.id, device)
                await db.commit()
                return str(device.id), tokens

        device, tokens = self.client.portal.call(seed)
        headers = {"Authorization": "Bearer " + tokens["accessToken"]}
        self.assertTrue(self.client.get("/auth/session/status", headers=headers).json()["ttsConsent"])
        self.assertEqual(self.client.put("/user/consents/tts", headers=headers, json={"agree": False}).status_code, 204)
        self.assertFalse(self.client.get("/auth/session/status", headers=headers).json()["ttsConsent"])
        self.assertEqual(self.client.delete("/device/" + device, headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/auth/session/status", headers=headers).status_code, 401)
        self.assertEqual(self.client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]}).status_code, 401)

    def test_attestation_parser_checks_boot_state_and_app_digest(self):
        from ieumsae_auth.attestation import parse_key_description

        def tlv(tag, value):
            length = len(value)
            size = bytes([length]) if length < 128 else bytes([0x82]) + length.to_bytes(2, 'big')
            return tag + size + value

        def sequence(value):
            return tlv(b'\x30', value)

        application = sequence(tlv(b'\x31', sequence(tlv(b'\x04', b'kr.ieumsae.app') + tlv(b'\x02', b'\x01')))
                               + tlv(b'\x31', tlv(b'\x04', bytes(32))))
        software = sequence(tlv(b'\xbf\x85\x45', tlv(b'\x04', application)))
        for locked in (True, False):
            boot = sequence(tlv(b'\x04', bytes(32)) + tlv(b'\x01', b'\xff' if locked else b'\x00')
                            + tlv(b'\x0a', b'\x00') + tlv(b'\x04', bytes(32)))
            hardware = sequence(tlv(b'\xbf\x85\x40', boot))
            description = sequence(tlv(b'\x02', b'\x04') + tlv(b'\x0a', b'\x01')
                                   + tlv(b'\x02', b'\x04') + tlv(b'\x0a', b'\x01')
                                   + tlv(b'\x04', b'challenge') + tlv(b'\x04', b'') + software + hardware)
            parsed = parse_key_description(description)
            self.assertEqual(parsed['package'], 'kr.ieumsae.app')
            self.assertEqual(parsed['digests'], ['0' * 64])
            self.assertEqual(parsed['locked'], locked)
            self.assertTrue(parsed['verified'])

    def test_revoked_device_certificate_is_rejected(self):
        import base64
        import time
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        from ieumsae_auth.revocation import RevocationChecker
        from ieumsae_auth.attestation import AttestationError
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(12345)
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                .sign(key, hashes.SHA256()))
        checker = RevocationChecker()
        checker.expires = time.monotonic() + 60
        checker.entries = frozenset({'3039'})
        encoded = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
        with self.assertRaisesRegex(AttestationError, 'certificate_revoked'):
            asyncio.run(checker.check([encoded]))

    def test_integrated_voice_and_auth_api(self):
        from api_flow import verify_api_flow
        verify_api_flow(self)

    def test_validation_does_not_echo_untrusted_fields(self):
        marker = "private-password-database-path"
        response = self.client.post("/auth/login", json={marker: marker})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        self.assertNotIn("fields", response.text)

    def test_mail_failure_returns_controlled_error(self):
        from ieumsae_auth import mailer
        with patch.object(mailer.aiosmtplib, "send", side_effect=OSError("private-smtp-password")):
            with self.assertLogs("ieumsae.mail", level="ERROR") as logs:
                response = self.client.post("/auth/email/code", json={"email": f"{secrets.token_hex(5)}@example.com"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "mail_unavailable"})
        self.assertNotIn("private-smtp-password", str(logs.output))

    def test_missing_integrity_token_is_rejected(self):
        from ieumsae_auth.integrity import IntegrityError, verify_integrity
        with self.assertRaises(IntegrityError):
            asyncio.run(verify_integrity(None, secrets.token_bytes(32)))

    def test_expired_attestation_certificate_is_rejected(self):
        import base64
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        from ieumsae_auth.attestation import AttestationError, verify_attestation
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, secrets.token_hex(8))])
        now = datetime.now(timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(days=2)).not_valid_after(now - timedelta(days=1))
                       .sign(key, hashes.SHA256()))
        encoded = base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()
        public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        with self.assertRaisesRegex(AttestationError, "유효기간"):
            verify_attestation([encoded, encoded], public, secrets.token_bytes(32))


if __name__ == "__main__":
    unittest.main()
