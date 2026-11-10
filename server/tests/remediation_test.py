"""Round-3 reproductions and compatibility checks. All credentials are disposable fixtures."""
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shared"))
from host_secrets import HEADER, PRIVATE_FILES, RUNTIME_FILES, SecretStore, SecretStoreError


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@unittest.skipUnless(os.name == "nt", "Windows DPAPI host provisioning")
class SecretStorageTest(unittest.TestCase):
    def test_concurrent_updates_fail_fast_and_retry_without_losing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SecretStore(Path(folder))
            entered, resume = threading.Event(), threading.Event()
            original = store._save
            def delayed(values):
                entered.set()
                if not resume.wait(5):
                    raise TimeoutError("test lock timeout")
                original(values)
            def first():
                with patch.object(store, "_save", side_effect=delayed):
                    store.put("db_password.txt", b"first-password")
            with ThreadPoolExecutor(max_workers=1) as pool:
                worker = pool.submit(first)
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaisesRegex(SecretStoreError, "BUSY"):
                        SecretStore(Path(folder)).put("smtp_password.txt", b"second-password")
                finally:
                    resume.set()
                worker.result(timeout=5)
            store.put("smtp_password.txt", b"second-password")
            self.assertEqual(store.load(), {"db_password.txt": b"first-password", "smtp_password.txt": b"second-password"})

    def test_generated_secrets_are_encrypted_and_rerun_preserves_consumers(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        generator = module("gen_keys_test", "tools/gen_keys.py")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            secret = root / "secrets"
            with patch.object(generator, "SECRETS", secret), patch.object(generator, "ANDROID_CFG", root / "android.properties"), patch.object(generator, "ANDROID_RES", root / "raw"), patch.object(sys, "argv", ["gen_keys", "--host", "localhost", "--signing-key-id", "test"]):
                generator.main()
                store = SecretStore(secret)
                values = store.load()
                ciphertext = store.path.read_bytes()
                self.assertTrue(ciphertext.startswith(HEADER))
                for name, value in values.items():
                    self.assertFalse((secret / name).exists(), name)
                    if value:
                        self.assertNotIn(value, ciphertext, name)
                before = (root / "android.properties").read_bytes()
                generator.main()
                self.assertEqual(store.load(), values)
                self.assertEqual((root / "android.properties").read_bytes(), before)
                for private, public in (("jwt_p256.pem", "jwt_p256.pub.pem"), ("stt_signing_p256.pem", "stt_signing_p256.pub.pem")):
                    key = serialization.load_pem_private_key(values[private], None)
                    actual = serialization.load_pem_public_key((secret / public).read_bytes())
                    self.assertEqual(key.public_key().public_numbers(), actual.public_numbers())
                key = AESGCM(base64.b64decode(values["profile_data_key.txt"]))
                encrypted = key.encrypt(b"0" * 12, b"existing-profile", b"user-id")
                restored = AESGCM(base64.b64decode(store.load()["profile_data_key.txt"]))
                self.assertEqual(restored.decrypt(b"0" * 12, encrypted, b"user-id"), b"existing-profile")

    def test_migration_preserves_every_byte_and_removes_plaintext(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = {name: ("fixture:" + name).encode() for name in PRIVATE_FILES}
            for name, value in original.items():
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(value)
            store = SecretStore(root)
            with self.assertRaisesRegex(SecretStoreError, "MIGRATION"):
                store.put("db_password.txt", b"must-not-rotate")
            self.assertEqual(store.migrate(), len(original))
            self.assertEqual(store.load(), original)
            self.assertTrue(all(not (root / name).exists() for name in original))
            self.assertEqual(store.migrate(), 0)

    def test_corruption_conflict_and_encryption_failure_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SecretStore(Path(folder))
            store.save({"db_password.txt": b"keep-existing-password"})
            before = store.path.read_bytes()
            legacy = store.directory / "db_password.txt"
            legacy.write_bytes(b"different-password")
            with self.assertRaisesRegex(SecretStoreError, "CONFLICT"):
                store.migrate()
            self.assertEqual(store.path.read_bytes(), before)
            self.assertTrue(legacy.exists())
            legacy.unlink()
            with patch("host_secrets._dpapi", side_effect=SecretStoreError("test")):
                with self.assertRaises(SecretStoreError):
                    store.save({"db_password.txt": b"replacement"})
            self.assertEqual(store.path.read_bytes(), before)
            tampered = bytearray(before)
            tampered[-1] ^= 1
            store.path.write_bytes(tampered)
            with self.assertRaises(SecretStoreError):
                store.load()

    def test_runtime_projection_preserves_formats_and_isolates_services(self):
        loader = module("secret_loader_test", "tools/secret_loader.py")
        self.assertEqual({k: set(v) for k, v in RUNTIME_FILES.items()}, loader.EXPECTED)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = SecretStore(root / "secrets")
            values = {name: ("fixture:" + name).encode() for name in PRIVATE_FILES}
            store.save(values)
            (store.directory / "jwt_p256.pub.pem").write_bytes(b"public-jwt")
            (store.directory / "tls").mkdir()
            (store.directory / "tls/server.pem").write_bytes(b"public-certificate")
            staging = root / "projection"
            for group in loader.EXPECTED:
                (staging / group).mkdir(parents=True)
            payload = store.runtime_payload()
            with patch.object(loader, "validate_mounts"):
                loader.project(payload, staging)
                loader.project(payload, staging)
                for group, mapping in RUNTIME_FILES.items():
                    self.assertEqual({p.name for p in (staging / group).iterdir()}, set(mapping))
                    for target, source in mapping.items():
                        expected = values[source] if source in PRIVATE_FILES else (store.directory / source).read_bytes()
                        self.assertEqual((staging / group / target).read_bytes(), expected)
                malicious = json.loads(payload)
                malicious["auth"]["../escape"] = base64.b64encode(b"secret").decode()
                with self.assertRaises(ValueError):
                    loader.project(json.dumps(malicious).encode(), staging)
                malicious = json.loads(payload)
                malicious["db"]["db_password"] = base64.b64encode(b"unexpected-rotation").decode()
                with self.assertRaisesRegex(ValueError, "ROTATION"):
                    loader.project(json.dumps(malicious).encode(), staging)
                self.assertEqual((staging / "db/db_password").read_bytes(), values["db_password.txt"])


class ProjectionMountTest(unittest.TestCase):
    def test_compose_smtp_true_is_accepted_and_tls_cannot_be_disabled(self):
        from pydantic import ValidationError
        with patch.dict(os.environ, {
            "AUTH_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "AUTH_SMTP_HOST": "smtp.example.invalid", "AUTH_MAIL_FROM": "proof@example.invalid",
            "AUTH_ANDROID_SIGNING_CERT_SHA256": "0" * 64,
            "AUTH_INTEGRITY_SERVICE_ACCOUNT_FILE": "not-used.json",
        }):
            Settings = module("smtp_config_test", "auth/ieumsae_auth/config.py").Settings
            for value in (True, "true", "True", "TRUE", "1"):
                self.assertIs(Settings(smtp_starttls=value).smtp_starttls, True)
            for value in (False, "false", "0", "", None):
                with self.assertRaises(ValidationError):
                    Settings(smtp_starttls=value)

    def test_disk_and_swappable_mounts_rejected(self):
        loader = module("secret_mount_test", "tools/secret_loader.py")
        for kind, options, allowed in (("ext4", "rw,noswap", False), ("tmpfs", "rw", False), ("tmpfs", "rw,noswap", True)):
            text = "\n".join(f"1 0 0:1 / /staging/{g} rw - {kind} tmpfs {options}" for g in loader.EXPECTED)
            with patch.object(Path, "read_text", return_value=text):
                if allowed:
                    loader.validate_mounts(PurePosixPath("/staging"))
                else:
                    with self.assertRaisesRegex(ValueError, "NON_MEMORY"):
                        loader.validate_mounts(PurePosixPath("/staging"))


class ExceptionBoundaryTest(unittest.TestCase):
    def assert_dispatch(self, function, expected_broad):
        """Observe executed handlers, not just the presence of an except clause."""
        tree = ast.parse(Path(function.__code__.co_filename).read_text(encoding="utf-8"))
        definition = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function.__name__)
        broad = next(n for n in ast.walk(definition) if isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name) and n.type.id == "Exception")
        lines = set()
        previous = sys.gettrace()
        def trace(frame, event, arg):
            if frame.f_code is function.__code__ and event == "line":
                lines.add(frame.f_lineno)
            return trace
        out, err = io.StringIO(), io.StringIO()
        try:
            sys.settrace(trace)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                result = function()
        finally:
            sys.settrace(previous)
        self.assertEqual(result, 1)
        self.assertEqual(any(n in lines for n in range(broad.body[0].lineno, broad.end_lineno + 1)), expected_broad)
        self.assertNotIn("SECRET-MARKER", out.getvalue() + err.getvalue())
        self.assertNotIn("Traceback", out.getvalue() + err.getvalue())
        return out.getvalue(), err.getvalue()

    def test_cli_expected_and_unexpected_failures_are_contained(self):
        exporter = module("export_model_test", "stt/tools/export_model.py")
        for name, path, entry, operation, errors, output in (
            ("gen_failure_test", "tools/gen_keys.py", "run", "main", (PermissionError, ValueError), "KEY_GENERATION_FAILED"),
            ("deploy_failure_test", "tools/deployment_check.py", "main", "check", (PermissionError, ValueError, AttributeError), 'deployment_check_failed'),
        ):
            value = module(name, path)
            for error in (*errors, AssertionError):
                with patch.object(value, operation, side_effect=error("SECRET-MARKER")):
                    stdout, stderr = self.assert_dispatch(getattr(value, entry), error is AssertionError)
                    self.assertIn(output, stdout + stderr)
        for error in (PermissionError, zipfile.BadZipFile, ValueError, RuntimeError, AssertionError):
            with patch.object(exporter, "main", side_effect=error("SECRET-MARKER")):
                stdout, stderr = self.assert_dispatch(exporter.run, error is AssertionError)
                self.assertEqual(stderr.strip(), "MODEL_EXPORT_FAILED")

    def test_startup_dispatch_and_success_keep_existing_contract(self):
        from ieumsae_shared import runtime
        import uvicorn
        for error in (ValueError, PermissionError, ImportError, RuntimeError, AssertionError):
            with patch.object(runtime, "configure_logging"), patch.object(sys, "argv", ["runtime", "auth"]), patch.object(uvicorn, "run", side_effect=error("SECRET-MARKER")), patch.dict(os.environ, {"TRUSTED_PROXY_IPS": "127.0.0.1"}):
                self.assert_dispatch(runtime.main, error is AssertionError)
        with patch.object(runtime, "configure_logging"), patch.object(sys, "argv", ["runtime", "auth"]), patch.object(uvicorn, "run") as serve, patch.dict(os.environ, {"TRUSTED_PROXY_IPS": "127.0.0.1"}):
            self.assertEqual(runtime.main(), 0)
            self.assertFalse(serve.call_args.kwargs["access_log"])
            self.assertFalse(serve.call_args.kwargs["server_header"])

    def test_export_integrity_failure_and_normal_roundtrip(self):
        import torch
        from ieumsae_stt.asr.model import SpeechTransformer
        exporter = module("export_roundtrip_test", "stt/tools/export_model.py")
        def factory(out_dim):
            return SpeechTransformer(out_dim=out_dim, hidden_dim=16, filter_dim=32, enc_n_layers=1, dec_n_layers=1, max_len=8)
        vocab = json.loads((ROOT / "stt/ieumsae_stt/asr/vocab.json").read_text())
        model = factory(len(vocab))
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "checkpoint.pth", Path(folder) / "model.pt"
            torch.save(model.state_dict(), source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            args = ["export", str(source), "--out", str(output), "--sha256", digest]
            with patch.object(sys, "argv", args), patch.object(exporter, "SpeechTransformer", side_effect=factory), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(exporter.run(), 0)
            restored = torch.load(output, weights_only=True)
            for name, tensor in model.state_dict().items():
                torch.testing.assert_close(restored[name], tensor)
            before = output.read_bytes()
            with patch.object(sys, "argv", args[:-1] + ["0" * 64]):
                self.assert_dispatch(exporter.run, False)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
