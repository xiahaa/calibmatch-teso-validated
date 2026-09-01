from __future__ import annotations

import numpy as np
import torch

from calibmatch_teso.patch_sampling import image_tensor, sample_feature_patches, sample_patches


def test_grid_sample_matches_analytic_subpixel_patch_on_affine_image() -> None:
    yy, xx = np.mgrid[:48, :64]
    image = np.stack((2.0 * xx + yy, xx + 3.0 * yy, 4.0 * xx - yy), axis=-1)
    image = np.ascontiguousarray(np.clip(image, 0, 255).astype(np.uint8))
    centers = np.array([[24.25, 20.75], [37.5, 28.125]], dtype=np.float32)
    offset_y, offset_x = np.mgrid[-4:5, -4:5]
    expected = []
    for center_x, center_y in centers:
        sample_x = center_x + offset_x
        sample_y = center_y + offset_y
        expected.append(
            np.stack(
                (
                    2.0 * sample_x + sample_y,
                    sample_x + 3.0 * sample_y,
                    4.0 * sample_x - sample_y,
                ),
                axis=-1,
            )
        )
    expected = np.stack(expected)
    actual = sample_patches(image_tensor(image, torch.device("cpu")), centers, size=9)
    actual = ((actual.permute(0, 2, 3, 1) + 1.0) * 127.5).numpy()
    np.testing.assert_allclose(actual, expected, atol=1.1)


def test_feature_patch_coordinate_scale() -> None:
    yy, xx = torch.meshgrid(torch.arange(24), torch.arange(32), indexing="ij")
    feature = (2.0 * xx + yy)[None, None].float()
    centers_image = np.array([[20.0, 16.0]], dtype=np.float32)
    patch = sample_feature_patches(feature, centers_image, size=5, stride=2.0)
    assert patch.shape == (1, 1, 5, 5)
    assert patch[0, 0, 2, 2].item() == feature[0, 0, 8, 10].item()
