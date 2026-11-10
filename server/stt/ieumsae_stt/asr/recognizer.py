import io
import json
import logging
import threading
from pathlib import Path

import numpy as np
import torch
from torchaudio.compliance import kaldi

from .model import SpeechTransformer

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
_VOCAB_PATH = Path(__file__).with_name("vocab.json")
_SPECIAL = {"<pad>", "<sos>", "<eos>"}


class Recognizer:
    def __init__(self, checkpoint: bytes, device: str = "auto"):

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        self.id2char: tuple[str, ...] = tuple(json.loads(_VOCAB_PATH.read_text(encoding="utf-8")))

        model = SpeechTransformer(out_dim=len(self.id2char))

        ckpt = torch.load(io.BytesIO(checkpoint), map_location="cpu", weights_only=True)
        state = ckpt.get("model_state_dict", ckpt)
        model.load_state_dict(state, strict=True)
        self.model = model.to(self.device).eval()

        self._lock = threading.Lock()
        log.info("STT 모델 로드 완료 (device=%s, vocab=%d)", self.device, len(self.id2char))

    def features(self, pcm: np.ndarray) -> torch.Tensor:

        sig = torch.from_numpy(pcm.astype(np.float32)).unsqueeze(0)
        fb = kaldi.fbank(
            sig,
            num_mel_bins=80,
            frame_length=25.0,
            frame_shift=10.0,
            sample_frequency=SAMPLE_RATE,
            window_type="hanning",
            dither=0.0,
        )
        return fb.unsqueeze(0)

    @staticmethod
    def has_speech(pcm: np.ndarray, min_voiced_sec: float = 0.25, rms_threshold: float = 150.0) -> bool:

        frame = SAMPLE_RATE // 50
        n = pcm.size // frame
        if n == 0:
            return False
        frames = pcm[: n * frame].astype(np.float32).reshape(n, frame)
        rms = np.sqrt(np.mean(frames * frames, axis=1))
        floor = float(np.percentile(rms, 10))
        voiced = rms > max(rms_threshold, floor * 3.0)
        return int(voiced.sum()) * 0.02 >= min_voiced_sec

    def transcribe_pcm16(self, pcm_bytes: bytes) -> str:
        if not isinstance(pcm_bytes, bytes) or len(pcm_bytes) % 2 or len(pcm_bytes) > SAMPLE_RATE * 2 * 30:
            raise ValueError("invalid_audio")
        pcm = np.frombuffer(pcm_bytes, dtype="<i2")
        if pcm.size < SAMPLE_RATE // 4 or not self.has_speech(pcm):
            return ""
        with self._lock:
            feats = self.features(pcm).to(self.device)
            if not torch.isfinite(feats).all():
                raise ValueError("invalid_features")
            ids = self.model.greedy_decode(feats)
        if any(not 0 <= i < len(self.id2char) for i in ids):
            raise ValueError("invalid_model_output")
        return "".join(self.id2char[i] for i in ids if self.id2char[i] not in _SPECIAL).strip()

    def warmup(self) -> None:
        feats = self.features(np.zeros(SAMPLE_RATE, dtype="<i2")).to(self.device)
        with self._lock:
            self.model.greedy_decode(feats)
