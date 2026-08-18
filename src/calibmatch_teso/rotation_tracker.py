from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import normalize, pixel_rays, so3_exp


@dataclass(frozen=True)
class RotationTrackerConfig:
    sigma: float = 1e-3
    update_bound: float = 2.5e-4
    burn_in: int = 10
    memory_max: float = 10.0
    curvature_floor: float = 1e-10


@dataclass(frozen=True)
class RotationObservation:
    rotation: np.ndarray
    update: np.ndarray
    update_applied: bool
    loss: float
    gradient: np.ndarray
    hessian: np.ndarray


class FullHessianRotationTracker:
    """TESO-kernel tracker on SO(3) with fixed translation direction."""

    def __init__(
        self,
        rotation_initial: np.ndarray,
        translation_direction: np.ndarray,
        config: RotationTrackerConfig | None = None,
    ) -> None:
        self.rotation = np.asarray(rotation_initial, dtype=np.float64).reshape(3, 3).copy()
        self.translation_direction = normalize(translation_direction)
        self.config = config or RotationTrackerConfig()
        if self.config.sigma <= 0 or self.config.update_bound <= 0:
            raise ValueError("sigma and update_bound must be positive")
        self.memory = np.ones(3, dtype=np.float64)
        self.mean_gradient = np.zeros(3, dtype=np.float64)
        self.mean_squared_gradient = np.zeros(3, dtype=np.float64)
        self.mean_hessian = np.zeros((3, 3), dtype=np.float64)
        self.burn_in_remaining = int(self.config.burn_in)

    def gradient_hessian_loss(
        self,
        left_xy: np.ndarray,
        right_xy: np.ndarray,
        k_left: np.ndarray,
        k_right: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        left = pixel_rays(left_xy, k_left)
        right = pixel_rays(right_xy, k_right)
        rotated = left @ self.rotation.T
        translation = self.translation_direction
        epipolar = np.sum(right * np.cross(translation[None, :], rotated), axis=1)
        derivative = np.empty((len(left), 3), dtype=np.float64)
        for index, axis in enumerate(np.eye(3)):
            rotated_derivative = np.cross(axis[None, :], rotated)
            derivative[:, index] = np.sum(
                right * np.cross(translation[None, :], rotated_derivative), axis=1
            )
        sigma_squared = self.config.sigma**2
        weights = np.exp(-0.5 * epipolar**2 / sigma_squared)
        # TESO evaluates each one-to-one pair in both matching directions.
        factor = 2.0
        gradient = factor * derivative.T @ (weights * epipolar / sigma_squared)
        curvature = weights * (
            1.0 / sigma_squared - epipolar**2 / sigma_squared**2
        )
        raw_hessian = factor * derivative.T @ (derivative * curvature[:, None])
        raw_hessian = 0.5 * (raw_hessian + raw_hessian.T)
        values, vectors = np.linalg.eigh(raw_hessian)
        hessian = (vectors * np.maximum(np.abs(values), self.config.curvature_floor)) @ vectors.T
        loss = float(1.0 - np.mean(weights)) if len(weights) else 1.0
        return gradient, hessian, loss

    def update(
        self,
        left_xy: np.ndarray,
        right_xy: np.ndarray,
        k_left: np.ndarray,
        k_right: np.ndarray,
    ) -> RotationObservation:
        gradient, hessian, loss = self.gradient_hessian_loss(
            left_xy, right_xy, k_left, k_right
        )
        inverse_memory = 1.0 / self.memory
        self.mean_gradient = (
            (1.0 - inverse_memory) * self.mean_gradient + inverse_memory * gradient
        )
        self.mean_squared_gradient = (
            (1.0 - inverse_memory) * self.mean_squared_gradient
            + inverse_memory * gradient**2
        )
        hessian_memory = float(np.mean(self.memory))
        self.mean_hessian = (
            (1.0 - 1.0 / hessian_memory) * self.mean_hessian
            + (1.0 / hessian_memory) * hessian
        )
        update = np.zeros(3, dtype=np.float64)
        learning_rate = self.mean_gradient**2 / (self.mean_squared_gradient + 1e-7)
        if self.burn_in_remaining > 1:
            self.memory += 1.0
            self.burn_in_remaining -= 1
        else:
            self.memory = np.clip(
                (1.0 - learning_rate) * self.memory + 1.0,
                1.0,
                self.config.memory_max,
            )
            update = -learning_rate * np.linalg.solve(
                self.mean_hessian
                + self.config.curvature_floor * np.eye(3, dtype=np.float64),
                gradient,
            )
            update = np.clip(
                update, -self.config.update_bound, self.config.update_bound
            )
            self.rotation = so3_exp(update) @ self.rotation
        return RotationObservation(
            rotation=self.rotation.copy(),
            update=update,
            update_applied=bool(np.linalg.norm(update) > 1e-15),
            loss=loss,
            gradient=gradient,
            hessian=hessian,
        )
