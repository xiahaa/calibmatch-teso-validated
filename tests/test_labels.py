from __future__ import annotations

import numpy as np

from calibmatch_teso.labels import interpolate_correspondence


def test_bilinear_interpolation_is_exact_for_affine_field() -> None:
    yy, xx = np.mgrid[:8, :10]
    correspondence = np.stack((1.2 * xx + 0.3 * yy, -0.2 * xx + 0.7 * yy), axis=-1)
    valid = np.ones((8, 10), dtype=bool)
    points = np.array([[2.25, 3.5], [4.25, 2.2]])
    labels = interpolate_correspondence(
        points, correspondence, valid, maximum_local_span=3.0
    )
    expected = np.column_stack(
        (1.2 * points[:, 0] + 0.3 * points[:, 1], -0.2 * points[:, 0] + 0.7 * points[:, 1])
    )
    assert labels.valid.all()
    np.testing.assert_allclose(labels.right_xy, expected, atol=1e-12)


def test_invalid_corner_or_discontinuity_is_rejected() -> None:
    correspondence = np.zeros((5, 5, 2), dtype=float)
    valid = np.ones((5, 5), dtype=bool)
    valid[2, 2] = False
    first = interpolate_correspondence(np.array([[1.5, 1.5]]), correspondence, valid)
    assert not first.valid[0]
    valid[:] = True
    correspondence[2, 2, 0] = 10.0
    second = interpolate_correspondence(np.array([[1.5, 1.5]]), correspondence, valid)
    assert not second.valid[0]
