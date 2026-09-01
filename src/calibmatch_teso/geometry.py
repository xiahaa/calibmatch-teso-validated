from __future__ import annotations

import numpy as np


def normalize(vector: np.ndarray, *, eps: float = 1e-12) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(norm) or norm < eps:
        raise ValueError("cannot normalize a zero or non-finite vector")
    return value / norm


def skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(vector, dtype=np.float64).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def so3_exp(rotation_vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(rotation_vector, dtype=np.float64).reshape(3)
    angle = float(np.linalg.norm(vector))
    generator = skew(vector)
    if angle < 1e-8:
        return np.eye(3) + generator + 0.5 * generator @ generator
    first = np.sin(angle) / angle
    second = (1.0 - np.cos(angle)) / (angle * angle)
    return np.eye(3) + first * generator + second * generator @ generator


def tangent_basis(direction: np.ndarray) -> np.ndarray:
    direction = normalize(direction)
    axis = np.eye(3)[int(np.argmin(np.abs(direction)))]
    first = normalize(np.cross(direction, axis))
    second = normalize(np.cross(direction, first))
    basis = np.column_stack((first, second))
    if np.linalg.det(np.column_stack((basis, direction))) < 0:
        basis[:, 1] *= -1.0
    return basis


def essential_from_pose(rotation: np.ndarray, direction: np.ndarray) -> np.ndarray:
    rotation = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    direction = normalize(direction)
    return skew(direction) @ rotation


def perturb_pose(
    rotation: np.ndarray,
    direction: np.ndarray,
    tangent: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    tangent = np.asarray(tangent, dtype=np.float64).reshape(5)
    direction = normalize(direction)
    basis = tangent_basis(direction)
    perturbed_rotation = so3_exp(tangent[:3]) @ np.asarray(rotation, dtype=np.float64)
    translation_rotation = so3_exp(basis @ tangent[3:])
    perturbed_direction = normalize(translation_rotation @ direction)
    return perturbed_rotation, perturbed_direction


def epipolar_residual_jacobian(
    left_rays: np.ndarray,
    right_rays: np.ndarray,
    rotation: np.ndarray,
    direction: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return algebraic epipolar residual and a 5-DoF left-tangent Jacobian."""

    left = np.asarray(left_rays, dtype=np.float64)
    right = np.asarray(right_rays, dtype=np.float64)
    if left.ndim != 2 or left.shape[1] != 3 or right.shape != left.shape:
        raise ValueError("left_rays and right_rays must both have shape (N,3)")
    rotation = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    direction = normalize(direction)
    essential = essential_from_pose(rotation, direction)
    residual = np.einsum("ni,ij,nj->n", right, essential, left)

    derivatives: list[np.ndarray] = []
    for axis in np.eye(3):
        derivatives.append(skew(direction) @ skew(axis) @ rotation)
    for basis_vector in tangent_basis(direction).T:
        direction_derivative = np.cross(basis_vector, direction)
        derivatives.append(skew(direction_derivative) @ rotation)
    jacobian = np.column_stack(
        [np.einsum("ni,ij,nj->n", right, derivative, left) for derivative in derivatives]
    )
    return residual, jacobian


def pixel_rays(points_xy: np.ndarray, intrinsic: np.ndarray) -> np.ndarray:
    points = np.asarray(points_xy, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("points_xy must have shape (N,2)")
    homogeneous = np.column_stack((points, np.ones(len(points), dtype=np.float64)))
    return (np.linalg.inv(np.asarray(intrinsic, dtype=np.float64)) @ homogeneous.T).T

