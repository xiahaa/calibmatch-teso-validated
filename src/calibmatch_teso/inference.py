from __future__ import annotations

import numpy as np
import torch

from .patch_sampling import image_tensor, sample_feature_patches, sample_patches
from .refiner import SubpixelStereoRefiner


@torch.inference_mode()
def refine_matches(
    model: SubpixelStereoRefiner,
    left_image: np.ndarray,
    right_image: np.ndarray,
    left_xy: np.ndarray,
    right_xy: np.ndarray,
    score: np.ndarray,
    device: torch.device,
    *,
    chunk: int = 512,
    backend: str = "patch",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    left_xy = np.asarray(left_xy)
    right_xy = np.asarray(right_xy)
    score = np.asarray(score)
    if left_xy.ndim != 2 or left_xy.shape[1:] != (2,):
        raise ValueError("left_xy must have shape (N,2)")
    if right_xy.shape != left_xy.shape:
        raise ValueError("right_xy must have the same shape as left_xy")
    if score.shape != (len(left_xy),):
        raise ValueError("score must have shape (N,)")
    if chunk <= 0:
        raise ValueError("chunk must be positive")
    if len(left_xy) == 0:
        return (
            np.empty((0, 2), dtype=np.float32),
            np.empty((0, 2), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
        )
    left_tensor = image_tensor(left_image, device)
    right_tensor = image_tensor(right_image, device)
    if backend not in {"patch", "dense"}:
        raise ValueError(f"unknown refiner backend: {backend}")
    left_dense = right_dense = None
    if backend == "dense":
        with torch.autocast(
            device_type="cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"
        ):
            left_dense = model.encoder(left_tensor)
            right_dense = model.encoder(right_tensor)
    deltas, sigmas, validities = [], [], []
    for start in range(0, len(left_xy), chunk):
        stop = min(start + chunk, len(left_xy))
        with torch.autocast(
            device_type="cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"
        ):
            score_tensor = torch.as_tensor(
                score[start:stop], device=device, dtype=torch.float32
            )
            if backend == "patch":
                output = model(
                    sample_patches(left_tensor, left_xy[start:stop]),
                    sample_patches(right_tensor, right_xy[start:stop]),
                    score_tensor,
                )
            else:
                assert left_dense is not None and right_dense is not None
                output = model.predict_encoded(
                    sample_feature_patches(left_dense, left_xy[start:stop]),
                    sample_feature_patches(right_dense, right_xy[start:stop]),
                    score_tensor,
                )
        deltas.append(output.delta_right_xy.float().cpu().numpy())
        sigmas.append(output.sigma_xy.float().cpu().numpy())
        validities.append(output.p_valid.float().cpu().numpy())
    return np.concatenate(deltas), np.concatenate(sigmas), np.concatenate(validities)
