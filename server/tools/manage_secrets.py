"""Import secrets from stdin; never accept secret values in arguments or environment."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from host_secrets import PRIVATE_FILES, SecretStore


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--migrate", action="store_true", help="기존 평문 파일을 값 변경 없이 암호화 저장 후 삭제")
    group.add_argument("--set", choices=sorted(PRIVATE_FILES), help="표준입력의 바이트를 암호화 저장")
    args = parser.parse_args()
    store = SecretStore(Path(__file__).resolve().parents[1] / "secrets")
    try:
        if args.migrate:
            store.migrate()
        else:
            value = sys.stdin.buffer.read(1024 * 1024 + 1)
            if not value or len(value) > 1024 * 1024:
                raise ValueError("invalid_secret_size")
            store.put(args.set, value, force=True)
    except (OSError, ValueError, TypeError):
        print("SECRET_UPDATE_FAILED", file=sys.stderr)
        return 1
    print("SECRET_UPDATE_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
