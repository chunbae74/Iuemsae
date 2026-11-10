"""Windows-host encrypted storage; plaintext exists only in process memory / Docker tmpfs."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager


HEADER = b"IEUMSAE-DPAPI-1\n"
PRIVATE_FILES = frozenset({
    "jwt_p256.pem", "stt_signing_p256.pem", "email_code_pepper.txt",
    "db_password.txt", "profile_data_key.txt", "smtp_password.txt",
    "integrity_service_account.json", "elevenlabs_api_key.txt", "tls/server.key",
})
RUNTIME_FILES = {
    "auth": {
        "db_password": "db_password.txt", "jwt_private": "jwt_p256.pem",
        "email_pepper": "email_code_pepper.txt", "profile_key": "profile_data_key.txt",
        "smtp_password": "smtp_password.txt", "integrity_account": "integrity_service_account.json",
    },
    "stt": {
        "jwt_public": "jwt_p256.pub.pem", "stt_signing": "stt_signing_p256.pem",
        "elevenlabs_api_key": "elevenlabs_api_key.txt",
    },
    "db": {"db_password": "db_password.txt"},
    "tls": {"server.key": "tls/server.key", "server.pem": "tls/server.pem"},
}


class SecretStoreError(ValueError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise SecretStoreError("WINDOWS_DPAPI_REQUIRED")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    protect = crypt.CryptProtectData
    unprotect = crypt.CryptUnprotectData
    common = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    protect.argtypes = common
    unprotect.argtypes = common
    protect.restype = unprotect.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    try:
        # UI_FORBIDDEN only: never enable machine-wide decryption.
        operation = unprotect if decrypt else protect
        if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
            raise SecretStoreError("SECRET_DECRYPTION_FAILED" if decrypt else "SECRET_ENCRYPTION_FAILED")
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if result.pbData:
            ctypes.memset(result.pbData, 0, result.cbData)
            kernel.LocalFree(result.pbData)


def _regular_path(path: Path) -> None:
    # Reject junctions as well as symlinks, including parent directories.
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            raise SecretStoreError("INVALID_SECRET_PATH")


class SecretStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "secrets.dpapi"

    def load(self) -> dict[str, bytes]:
        _regular_path(self.path)
        if not self.path.exists():
            return {}
        blob = self.path.read_bytes()
        if not blob.startswith(HEADER):
            raise SecretStoreError("INVALID_SECRET_STORE")
        payload = json.loads(_dpapi(blob[len(HEADER):], decrypt=True))
        if not isinstance(payload, dict) or set(payload) - PRIVATE_FILES:
            raise SecretStoreError("INVALID_SECRET_STORE")
        try:
            return {name: base64.b64decode(value, validate=True) for name, value in payload.items()}
        except (TypeError, ValueError) as error:
            raise SecretStoreError("INVALID_SECRET_STORE") from error

    @contextmanager
    def _locked(self):
        if os.name != "nt":
            raise SecretStoreError("WINDOWS_DPAPI_REQUIRED")
        import msvcrt
        lock_path = self.directory / "secrets.lock"
        _regular_path(lock_path)
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise SecretStoreError("SECRET_STORE_BUSY") from error
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(descriptor)

    def save(self, values: dict[str, bytes]) -> None:
        with self._locked():
            self._save(values)

    def _save(self, values: dict[str, bytes]) -> None:
        if set(values) - PRIVATE_FILES:
            raise SecretStoreError("INVALID_SECRET_NAME")
        plaintext = json.dumps({k: base64.b64encode(v).decode("ascii") for k, v in values.items()}).encode()
        ciphertext = HEADER + _dpapi(plaintext, decrypt=False)
        _regular_path(self.path)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as staging:
                temporary = Path(staging.name)
                staging.write(ciphertext)
                staging.flush()
                os.fsync(staging.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def require_migrated(self) -> None:
        for name in PRIVATE_FILES:
            path = self.directory / name
            _regular_path(path)
            if path.exists():
                raise SecretStoreError("PLAINTEXT_SECRETS_REQUIRE_MIGRATION")

    def put(self, name: str, data: bytes, force: bool = False) -> bool:
        if name not in PRIVATE_FILES:
            raise SecretStoreError("INVALID_SECRET_NAME")
        with self._locked():
            self.require_migrated()
            values = self.load()
            if name in values and not force:
                return False
            values[name] = data
            self._save(values)
            return True

    def migrate(self) -> int:
        """Preserve identities; verify the encrypted commit before removing old files."""
        with self._locked():
            return self._migrate()

    def _migrate(self) -> int:
        values = self.load()
        legacy = []
        for name in sorted(PRIVATE_FILES):
            path = self.directory / name
            _regular_path(path)
            if path.is_file():
                data = path.read_bytes()
                if name in values and values[name] != data:
                    raise SecretStoreError("SECRET_MIGRATION_CONFLICT")
                values[name] = data
                legacy.append(path)
        if legacy:
            self._save(values)
            if self.load() != values:
                raise SecretStoreError("SECRET_MIGRATION_FAILED")
            for path in legacy:
                path.unlink()
        return len(legacy)

    def runtime_payload(self) -> bytes:
        self.require_migrated()
        values = self.load()
        payload = {}
        for group, files in RUNTIME_FILES.items():
            payload[group] = {}
            for target, source in files.items():
                if source in PRIVATE_FILES:
                    data = values.get(source)
                else:
                    path = self.directory / source
                    _regular_path(path)
                    data = path.read_bytes()
                if not data:
                    raise SecretStoreError("SECRET_FILES_REQUIRED")
                payload[group][target] = base64.b64encode(data).decode("ascii")
        return json.dumps(payload).encode()
