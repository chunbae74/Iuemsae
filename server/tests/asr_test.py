import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stt"))

from ieumsae_stt.asr.model import SpeechTransformer


class SpeechModelTest(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.model = SpeechTransformer(out_dim=16, hidden_dim=16, filter_dim=32,
                                       enc_n_layers=1, dec_n_layers=1, max_len=8).eval()

    def test_decoder_cannot_read_future_tokens(self):
        inputs = torch.randn(1, 32, 80)
        with torch.inference_mode():
            memory, _ = self.model.encoder(self.model.conv(inputs))
            first = torch.tensor([[1, 3, 4]])
            second = torch.tensor([[1, 8, 9]])
            mask = ~torch.tril(torch.ones(3, 3, dtype=torch.bool)).view(1, 1, 3, 3)
            a = self.model.decoder(first, mask, memory, None)
            b = self.model.decoder(second, mask, memory, None)
            torch.testing.assert_close(a[:, 0], b[:, 0])
            self.assertTrue(torch.isfinite(a).all())

    def test_inference_is_deterministic(self):
        inputs = torch.randn(1, 32, 80)
        first = self.model.greedy_decode(inputs)
        second = self.model.greedy_decode(inputs)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), self.model.max_len)


if __name__ == "__main__":
    unittest.main()
