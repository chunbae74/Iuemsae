import argparse
import hashlib
import hmac
import os
import io
import sys
import tempfile
import zipfile
import pickle
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ieumsae_stt.asr.model import SpeechTransformer

CKPT_SUFFIX = "kosr/checkpoint/best_wer.pth"


def _name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except UnicodeError:
        return info.filename


MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024


def _copy_entry(z, info, out):
    if info.file_size > MAX_ARCHIVE_BYTES or info.file_size > max(info.compress_size, 1) * 200:
        raise ValueError("archive_limit")
    total = 0
    with z.open(info) as src, open(out, "xb") as dst:
        while chunk := src.read(1 << 20):
            total += len(chunk)
            if total > MAX_ARCHIVE_BYTES:
                raise ValueError("archive_limit")
            dst.write(chunk)


def _find_in_zip(z: zipfile.ZipFile, tmp: Path, depth=0) -> Path | None:
    if depth > 2 or len(z.infolist()) > 20000:
        raise ValueError("archive_limit")
    for info in z.infolist():
        name = _name(info).replace("\\", "/")
        if name.endswith(CKPT_SUFFIX):
            out = tmp / "best_wer.pth"
            _copy_entry(z, info, out)
            return out
    for info in z.infolist():
        if _name(info).endswith("인식모델.zip"):
            inner = tmp / f"inner-{depth}.zip"
            _copy_entry(z, info, inner)
            with zipfile.ZipFile(inner) as z2:
                return _find_in_zip(z2, tmp, depth + 1)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="best_wer.pth 또는 AI 모델 소스코드.zip / 4_인식모델.zip")
    ap.add_argument("--out", default=str(ROOT / "models" / "ieumsae_stt.pt"))
    ap.add_argument("--sha256", required=True, help="신뢰한 원본 체크포인트의 SHA-256")
    args = ap.parse_args()

    src = Path(args.source)
    if src.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive_limit")
    with tempfile.TemporaryDirectory() as td:
        if src.suffix.lower() == ".zip":
            with zipfile.ZipFile(src) as z:
                ckpt = _find_in_zip(z, Path(td))
            if ckpt is None:
                sys.exit("압축 파일 안에서 best_wer.pth를 찾지 못했습니다")
        else:
            ckpt = src
        with ckpt.open("rb") as handle:
            blob = handle.read(MAX_ARCHIVE_BYTES + 1)
        if len(blob) > MAX_ARCHIVE_BYTES or not hmac.compare_digest(hashlib.sha256(blob).hexdigest(), args.sha256.lower()):
            raise ValueError("checkpoint_integrity")
        data = torch.load(io.BytesIO(blob), map_location="cpu", weights_only=True)
        del blob
        state = data.get("model_state_dict", data)

    vocab = (ROOT / "ieumsae_stt" / "asr" / "vocab.json").read_text(encoding="utf-8")
    import json

    model = SpeechTransformer(out_dim=len(json.loads(vocab)))
    model.load_state_dict(state, strict=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    with tempfile.NamedTemporaryFile(dir=out.parent, delete=False) as staging:
        temporary = Path(staging.name)
        staging.write(buf.getvalue())
    try:
        os.replace(temporary, out)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(buf.getvalue()).hexdigest()

    Path(str(out) + ".sha256").write_text(f"{digest}  {out.name}\n", encoding="ascii")
    print("MODEL_EXPORT_COMPLETE")


def run() -> int:
    try:
        main()
    except (OSError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile):
        print("MODEL_EXPORT_FAILED", file=sys.stderr)
        return 1
    except (ValueError, TypeError, KeyError, RuntimeError, pickle.UnpicklingError):
        print("MODEL_EXPORT_FAILED", file=sys.stderr)
        return 1
    except Exception:
        # Unexpected library failures must also keep checkpoint data private.
        print("MODEL_EXPORT_FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
