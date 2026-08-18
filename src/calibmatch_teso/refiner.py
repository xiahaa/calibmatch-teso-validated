from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
import torch.nn.functional as functional


@dataclass
class RefinerOutput:
    delta_right_xy: torch.Tensor
    sigma_xy: torch.Tensor
    p_valid: torch.Tensor
    valid_logit: torch.Tensor
    offset_logits: torch.Tensor


class PatchEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        channels = (3, 32, 32, 64, 64)
        layers: list[nn.Module] = []
        for index in range(4):
            layers.append(
                nn.Conv2d(
                    channels[index],
                    channels[index + 1],
                    kernel_size=3,
                    stride=2 if index == 0 else 1,
                    padding=1,
                )
            )
            layers.append(nn.GroupNorm(8, channels[index + 1]))
            layers.append(nn.GELU())
        self.network = nn.Sequential(*layers)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.network(image)


class SubpixelStereoRefiner(nn.Module):
    """Refine frozen LightGlue right endpoints without calibration input."""

    def __init__(self) -> None:
        super().__init__()
        self.encoder = PatchEncoder()
        context_channels = 81 + 64 + 64 + 1
        self.head = nn.Sequential(
            nn.Linear(context_channels, 256),
            nn.GELU(),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, 81 + 2 + 2),
        )
        validity_channels = context_channels + 64 + 64 + 64 + 3
        self.validity_head = nn.Sequential(
            nn.Linear(validity_channels, 256),
            nn.GELU(),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, 1),
        )
        y, x = torch.meshgrid(torch.arange(-4, 5), torch.arange(-4, 5), indexing="ij")
        self.register_buffer("offsets", 2.0 * torch.stack((x, y), dim=-1).reshape(81, 2).float())

    def forward(
        self,
        left_patch: torch.Tensor,
        right_patch: torch.Tensor,
        lightglue_score: torch.Tensor,
    ) -> RefinerOutput:
        left_feature = self.encoder(left_patch)
        right_feature = self.encoder(right_patch)
        return self.predict_encoded(left_feature, right_feature, lightglue_score)

    def predict_encoded(
        self,
        left_feature: torch.Tensor,
        right_feature: torch.Tensor,
        lightglue_score: torch.Tensor,
    ) -> RefinerOutput:
        if left_feature.shape != right_feature.shape:
            raise ValueError("left/right encoded patches must have identical shapes")
        if left_feature.ndim != 4 or left_feature.shape[1:] != (64, 17, 17):
            raise ValueError("encoded patches must have shape (N,64,17,17)")
        if lightglue_score.shape != (left_feature.shape[0],):
            raise ValueError("lightglue_score must have shape (N,)")
        center = left_feature.shape[-1] // 2
        left_center = functional.normalize(left_feature[:, :, center, center], dim=1)
        right_center = functional.normalize(right_feature[:, :, center, center], dim=1)
        left_support = left_feature[:, :, center - 2 : center + 3, center - 2 : center + 3].flatten(1)
        left_support = functional.normalize(left_support, dim=1)
        right_region = right_feature[:, :, center - 6 : center + 7, center - 6 : center + 7]
        right_support = functional.unfold(right_region, kernel_size=5).transpose(1, 2)
        right_support = functional.normalize(right_support, dim=2)
        correlation = torch.einsum("nc,nkc->nk", left_support, right_support)
        context = torch.cat((correlation, left_center, right_center, lightglue_score[:, None]), dim=1)
        prediction = self.head(context)
        logits = prediction[:, :81]
        residual = torch.tanh(prediction[:, 81:83])
        sigma = functional.softplus(prediction[:, 83:85]) + 0.05
        sigma = sigma.clamp(max=8.0)
        probability = torch.softmax(logits.float() / 0.25, dim=1).to(logits.dtype)
        delta = probability @ self.offsets.to(probability.dtype) + residual
        delta = delta.clamp(min=-8.0, max=8.0)
        left_pool = left_feature.mean(dim=(2, 3))
        right_pool = right_feature.mean(dim=(2, 3))
        correlation_probability = torch.softmax(correlation.float() / 0.25, dim=1).to(correlation.dtype)
        top_two = torch.topk(correlation, k=2, dim=1).values
        statistics = torch.stack(
            (
                correlation.max(dim=1).values,
                top_two[:, 0] - top_two[:, 1],
                -(correlation_probability * torch.log(correlation_probability.clamp_min(1e-6))).sum(dim=1),
            ),
            dim=1,
        )
        validity_context = torch.cat(
            (context, left_pool, right_pool, torch.abs(left_center - right_center), statistics), dim=1
        )
        valid_logit = self.validity_head(validity_context)[:, 0]
        p_valid = torch.sigmoid(valid_logit)
        return RefinerOutput(delta, sigma, p_valid, valid_logit, logits)
