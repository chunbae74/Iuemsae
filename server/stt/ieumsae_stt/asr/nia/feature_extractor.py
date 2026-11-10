import torch
import torch.nn as nn


class VGGExtractor(nn.Module):
    def __init__(self, in_dim=80, feature_dim=128, hidden_dim=512, proj_dropout_rate=0.1):
        super(VGGExtractor,self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 64, 3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 64, 3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, stride=2),
            nn.Conv2d(64, 128, 3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv2d(128, feature_dim, 3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, stride=2)
        )
        sub_sampling_dim = in_dim>>2
        self.post_extract_proj = nn.Linear(sub_sampling_dim*feature_dim, hidden_dim)


    def forward(self, x):
        x = x.unsqueeze(1)
        x = self.conv(x)
        B,C,T,F = x.size()
        x = self.post_extract_proj(x.transpose(1,2).contiguous().view(B,T,C*F))

        return x
