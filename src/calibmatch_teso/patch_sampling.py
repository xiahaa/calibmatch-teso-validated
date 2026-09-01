from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as functional


def image_tensor(image_rgb: np.ndarray, device: torch.device) -> torch.Tensor:
    array = np.ascontiguousarray(image_rgb)
    return (
        torch.from_numpy(array)
        .to(device=device, non_blocking=True)
        .permute(2, 0, 1)[None]
        .float()
        .div_(127.5)
        .sub_(1.0)
    )


def sample_patches(
    image: torch.Tensor,
    centers_xy: np.ndarray | torch.Tensor,
    *,
    size: int = 33,
) -> torch.Tensor:
    if image.ndim != 4 or image.shape[0] != 1:
        raise ValueError("image must have shape (1,C,H,W)")
    if size <= 0 or size % 2 != 1:
        raise ValueError("patch size must be positive and odd")
    centers = torch.as_tensor(centers_xy, dtype=torch.float32, device=image.device)
    if centers.ndim != 2 or centers.shape[1] != 2:
        raise ValueError("centers_xy must have shape (N,2)")
    radius = size // 2
    offset = torch.arange(-radius, radius + 1, device=image.device, dtype=torch.float32)
    y, x = torch.meshgrid(offset, offset, indexing="ij")
    grid = centers[:, None, None, :] + torch.stack((x, y), dim=-1)[None]
    height, width = image.shape[-2:]
    grid_x = 2.0 * grid[..., 0] / max(width - 1, 1) - 1.0
    grid_y = 2.0 * grid[..., 1] / max(height - 1, 1) - 1.0
    normalized = torch.stack((grid_x, grid_y), dim=-1)
    return functional.grid_sample(
        image.expand(len(centers), -1, -1, -1),
        normalized,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )


def sample_feature_patches(
    feature: torch.Tensor,
    centers_xy: np.ndarray | torch.Tensor,
    *,
    size: int = 17,
    stride: float = 2.0,
) -> torch.Tensor:
    """Sample local windows from a once-encoded full-image feature map.

    A stride-2, kernel-3, padding-1 convolution maps input coordinate ``x``
    to feature coordinate ``x/2``. Keeping this transform explicit avoids
    silently treating feature indices as image pixels.
    """
    if stride <= 0:
        raise ValueError("stride must be positive")
    centers = torch.as_tensor(centers_xy, dtype=torch.float32, device=feature.device)
    return sample_patches(feature, centers / stride, size=size)
