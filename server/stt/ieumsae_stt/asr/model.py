import torch
import torch.nn as nn

from .nia.feature_extractor import VGGExtractor
from .nia.encoder import Encoder
from .nia.decoder import Decoder


class SpeechTransformer(nn.Module):


    def __init__(self, out_dim, in_dim=80, enc_n_layers=12, dec_n_layers=6, hidden_dim=512,
                 filter_dim=2048, n_head=1, max_len=150, sos_id=1, eos_id=2):
        super().__init__()
        if not 1 <= max_len <= 150 or not 0 <= sos_id < out_dim or not 0 <= eos_id < out_dim:
            raise ValueError("invalid_decoder_limits")
        self.max_len = max_len
        self.sos_id = sos_id
        self.eos_id = eos_id
        self.conv = VGGExtractor(in_dim=in_dim, hidden_dim=hidden_dim)
        self.encoder = Encoder(hidden_dim, filter_dim, n_head, 0.1, enc_n_layers)
        self.decoder = Decoder(out_dim, hidden_dim, filter_dim, n_head, 0.1, dec_n_layers)

    @torch.inference_mode()
    def greedy_decode(self, feats: torch.Tensor) -> list[int]:

        if feats.ndim != 3 or feats.shape[0] != 1 or feats.shape[2] != 80 or not 1 <= feats.shape[1] <= 3000:
            raise ValueError("invalid_features")
        enc_out, _ = self.encoder(self.conv(feats))
        ys = torch.full((1, 1), self.sos_id, dtype=torch.long, device=feats.device)
        out: list[int] = []
        for step in range(self.max_len):
            n = step + 1
            tgt_mask = ~torch.tril(torch.ones(n, n, dtype=torch.bool, device=feats.device))
            logits = self.decoder(ys, tgt_mask.view(1, 1, n, n), enc_out, None)
            nxt = int(logits[0, -1].argmax())
            if nxt == self.eos_id:
                break
            out.append(nxt)
            ys = torch.cat([ys, torch.tensor([[nxt]], device=feats.device)], dim=1)
        return out
