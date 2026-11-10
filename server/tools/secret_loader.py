"""Container-side stdin projection. Refuse disk-backed or swappable secret mounts."""
import base64
import json
import os
from pathlib import Path
import sys


EXPECTED = {
    "auth": {"db_password", "jwt_private", "email_pepper", "profile_key", "smtp_password", "integrity_account"},
    "stt": {"jwt_public", "stt_signing", "elevenlabs_api_key"},
    "db": {"db_password"},
    "tls": {"server.key", "server.pem"},
}


def validate_mounts(root: Path) -> None:
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields = right.split()
        mounts[left.split()[4]] = (fields[0], set(fields[2].split(",")))
    for group in EXPECTED:
        kind, options = mounts.get(str(root / group), (None, set()))
        if kind != "tmpfs" or "noswap" not in options:
            raise ValueError("NON_MEMORY_SECRET_MOUNT")


def project(payload: bytes, root: Path) -> None:
    data = json.loads(payload)
    if not isinstance(data, dict) or set(data) != set(EXPECTED):
        raise ValueError("INVALID_SECRET_PAYLOAD")
    decoded = {}
    for group, names in EXPECTED.items():
        if not isinstance(data[group], dict) or set(data[group]) != names:
            raise ValueError("INVALID_SECRET_PAYLOAD")
        for name in names:
            value = base64.b64decode(data[group][name], validate=True)
            if not value or len(value) > 1024 * 1024:
                raise ValueError("INVALID_SECRET_SIZE")
            decoded[group, name] = value
    validate_mounts(root)
    for (group, name), value in decoded.items():
        directory = root / group
        path = directory / name
        if path.is_symlink():
            raise ValueError("INVALID_SECRET_PATH")
        # Never replace live secrets underneath running readers.
        if path.exists():
            if path.read_bytes() != value:
                raise ValueError("SECRET_ROTATION_REQUIRES_STOP")
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)


def main() -> int:
    try:
        payload = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("INVALID_SECRET_SIZE")
        project(payload, Path("/staging"))
    except (OSError, ValueError, TypeError, KeyError):
        print("SECRET_PROJECTION_FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
