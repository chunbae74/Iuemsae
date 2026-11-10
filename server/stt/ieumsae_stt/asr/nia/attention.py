import math
import numpy
import torch
from torch import nn


class MultiHeadAttention(nn.Module):
    def __init__(self, hidden_dim, n_head, dropout_rate):
        super(MultiHeadAttention, self).__init__()
        if n_head <= 0 or hidden_dim <= 0 or hidden_dim % n_head != 0:
            raise ValueError("invalid_attention_dimensions")

        self.d_k = hidden_dim // n_head
        self.n_head = n_head
        self.w_q = nn.Linear(hidden_dim, hidden_dim)
        self.w_k = nn.Linear(hidden_dim, hidden_dim)
        self.w_v = nn.Linear(hidden_dim, hidden_dim)
        self.out_proj = nn.Linear(hidden_dim, hidden_dim)
        self.dropout = nn.Dropout(p=dropout_rate)

    def forward_qkv(self, query, key, value):
        btz = query.size(0)
        q = self.w_q(query).view(btz, -1, self.n_head, self.d_k)
        k = self.w_k(key).view(btz, -1, self.n_head, self.d_k)
        v = self.w_v(value).view(btz, -1, self.n_head, self.d_k)
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        return q, k, v

    def forward_attention(self, value, scores, mask):
        n_batch = value.size(0)

        if mask is not None:
            min_value = float(
                numpy.finfo(torch.tensor(0, dtype=scores.dtype).numpy().dtype).min
            )
            scores = scores.masked_fill(mask, min_value)
            attn = torch.softmax(scores, dim=-1).masked_fill(mask, 0.0)
        else:
            attn = torch.softmax(scores, dim=-1)

        p_attn = self.dropout(attn)
        x = torch.matmul(p_attn, value)
        x = (x.transpose(1, 2).contiguous().view(n_batch, -1, self.n_head * self.d_k))

        return self.out_proj(x)

    def forward(self, query, key, value, mask=None):
        btz = query.size(0)

        q, k, v = self.forward_qkv(query, key, value)

        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.d_k)
        return self.forward_attention(v, scores, mask)
