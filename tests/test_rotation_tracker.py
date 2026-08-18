from __future__ import annotations

import numpy as np

from calibmatch_teso.geometry import so3_exp
from calibmatch_teso.rotation_tracker import FullHessianRotationTracker


def test_rotation_kernel_gradient_matches_finite_difference() -> None:
    rng = np.random.default_rng(23)
    intrinsic = np.array(
        [[700.0, 0.0, 512.0], [0.0, 700.0, 256.0], [0.0, 0.0, 1.0]]
    )
    left = rng.uniform([20.0, 20.0], [1000.0, 490.0], size=(80, 2))
    right = left + rng.normal(scale=1.0, size=(80, 2))
    rotation = so3_exp(np.array([0.001, -0.002, 0.0005]))
    tracker = FullHessianRotationTracker(rotation, np.array([-1.0, 0.0, 0.0]))
    gradient, hessian, _ = tracker.gradient_hessian_loss(
        left, right, intrinsic, intrinsic
    )
    epsilon = 1e-7
    numeric = np.empty(3)
    original = tracker.rotation.copy()
    for index in range(3):
        tangent = np.zeros(3)
        tangent[index] = epsilon
        tracker.rotation = so3_exp(tangent) @ original
        plus = tracker.gradient_hessian_loss(left, right, intrinsic, intrinsic)[2]
        tracker.rotation = so3_exp(-tangent) @ original
        minus = tracker.gradient_hessian_loss(left, right, intrinsic, intrinsic)[2]
        numeric[index] = (plus - minus) / (2.0 * epsilon) * (2.0 * len(left))
    tracker.rotation = original
    np.testing.assert_allclose(gradient, numeric, rtol=2e-4, atol=1e-5)
    np.testing.assert_allclose(hessian, hessian.T, atol=1e-12)
    assert np.linalg.eigvalsh(hessian).min() > 0.0


def test_rotation_tracker_keeps_translation_fixed_and_updates_after_burnin() -> None:
    intrinsic = np.array(
        [[700.0, 0.0, 512.0], [0.0, 700.0, 256.0], [0.0, 0.0, 1.0]]
    )
    left = np.array([[400.0, 200.0], [600.0, 220.0], [800.0, 300.0]])
    right = left + np.array([[-20.0, 0.2], [-18.0, -0.1], [-22.0, 0.15]])
    direction = np.array([-1.0, 0.0, 0.0])
    tracker = FullHessianRotationTracker(np.eye(3), direction)
    observations = [tracker.update(left, right, intrinsic, intrinsic) for _ in range(10)]
    np.testing.assert_allclose(tracker.translation_direction, direction)
    assert not any(row.update_applied for row in observations[:9])
    assert observations[9].update.shape == (3,)
