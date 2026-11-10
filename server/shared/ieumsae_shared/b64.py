import base64
import binascii


class B64Error(ValueError):
    pass


def b64e(data: bytes) -> str:

    return base64.b64encode(data).decode("ascii")


def b64d(text: str, *, max_len: int | None = None) -> bytes:

    if not isinstance(text, str):
        raise B64Error("base64 문자열이 아닙니다")
    if max_len is not None and len(text) > max_len * 4 // 3 + 4:
        raise B64Error("값이 너무 깁니다")
    s = text.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        out = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as e:
        raise B64Error("base64 형식이 아닙니다") from e
    if max_len is not None and len(out) > max_len:
        raise B64Error("값이 너무 깁니다")
    return out
