from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CorrespondenceLabels:
    right_xy: np.ndarray
    valid: np.ndarray
    local_span_xy: np.ndarray


def interpolate_correspondence(
    left_xy: np.ndarray,
    correspondence_xy: np.ndarray,
    valid_map: np.ndarray,
    *,
    maximum_local_span: float = 2.0,
) -> CorrespondenceLabels:
    """Bilinearly sample dense correspondence labels with edge rejection."""

    points = np.asarray(left_xy, dtype=np.float64)
    correspondence = np.asarray(correspondence_xy, dtype=np.float64)
    valid_dense = np.asarray(valid_map, dtype=bool)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("left_xy must have shape (N,2)")
    if correspondence.ndim != 3 or correspondence.shape[2] != 2:
        raise ValueError("correspondence_xy must have shape (H,W,2)")
    if valid_dense.shape != correspondence.shape[:2]:
        raise ValueError("valid_map shape must match correspondence_xy")
    if maximum_local_span <= 0:
        raise ValueError("maximum_local_span must be positive")

    height, width = valid_dense.shape
    x = points[:, 0]
    y = points[:, 1]
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    inside = (
        np.isfinite(points).all(axis=1)
        & (x0 >= 0)
        & (y0 >= 0)
        & (x0 + 1 < width)
        & (y0 + 1 < height)
    )
    safe_x0 = np.clip(x0, 0, width - 2)
    safe_y0 = np.clip(y0, 0, height - 2)
    corners = np.stack(
        (
            correspondence[safe_y0, safe_x0],
            correspondence[safe_y0, safe_x0 + 1],
            correspondence[safe_y0 + 1, safe_x0],
            correspondence[safe_y0 + 1, safe_x0 + 1],
        ),
        axis=1,
    )
    corner_valid = np.stack(
        (
            valid_dense[safe_y0, safe_x0],
            valid_dense[safe_y0, safe_x0 + 1],
            valid_dense[safe_y0 + 1, safe_x0],
            valid_dense[safe_y0 + 1, safe_x0 + 1],
        ),
        axis=1,
    ).all(axis=1)
    local_span = np.ptp(corners, axis=1)
    smooth = np.all(local_span < maximum_local_span, axis=1)
    finite = np.isfinite(corners).all(axis=(1, 2))

    dx = (x - safe_x0).reshape(-1, 1)
    dy = (y - safe_y0).reshape(-1, 1)
    sampled = (
        corners[:, 0] * (1.0 - dx) * (1.0 - dy)
        + corners[:, 1] * dx * (1.0 - dy)
        + corners[:, 2] * (1.0 - dx) * dy
        + corners[:, 3] * dx * dy
    )
    target_inside = (
        (sampled[:, 0] >= 0.0)
        & (sampled[:, 0] <= width - 1.0)
        & (sampled[:, 1] >= 0.0)
        & (sampled[:, 1] <= height - 1.0)
    )
    valid = inside & corner_valid & smooth & finite & target_inside
    sampled[~valid] = np.nan
    return CorrespondenceLabels(sampled, valid, local_span)

