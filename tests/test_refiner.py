from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from calibmatch_teso.inference import refine_matches
from calibmatch_teso.refiner import SubpixelStereoRefiner


def test_refiner_shapes_and_bounds() -> None:
    torch.manual_seed(2)
    model = SubpixelStereoRefiner()
    output = model(
        torch.randn(3, 3, 33, 33),
        torch.randn(3, 3, 33, 33),
        torch.tensor([0.2, 0.5, 0.9]),
    )
    assert output.delta_right_xy.shape == (3, 2)
    assert output.sigma_xy.shape == (3, 2)
    assert output.p_valid.shape == (3,)
    assert torch.all(torch.abs(output.delta_right_xy) <= 8.0)
    assert torch.all((output.sigma_xy >= 0.05) & (output.sigma_xy <= 8.0))


def test_released_checkpoints_load_strictly() -> None:
    root = Path(__file__).resolve().parents[1]
    for checkpoint in sorted((root / "checkpoints").glob("*.pt")):
        stored = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model = SubpixelStereoRefiner()
        model.load_state_dict(stored["model"], strict=True)


def test_selected_checkpoint_runs_end_to_end() -> None:
    root = Path(__file__).resolve().parents[1]
    stored = torch.load(
        root / "checkpoints" / "seed37_step20000.pt",
        map_location="cpu",
        weights_only=True,
    )
    model = SubpixelStereoRefiner()
    model.load_state_dict(stored["model"], strict=True)
    model.eval()
    image = np.zeros((64, 96, 3), dtype=np.uint8)
    left_xy = np.asarray([[32.0, 32.0], [48.25, 28.5]], dtype=np.float32)
    right_xy = left_xy - np.asarray([[4.0, 0.0], [5.0, 0.0]], dtype=np.float32)
    delta, sigma, p_valid = refine_matches(
        model,
        image,
        image,
        left_xy,
        right_xy,
        np.asarray([0.9, 0.8], dtype=np.float32),
        torch.device("cpu"),
        chunk=1,
    )
    assert delta.shape == sigma.shape == (2, 2)
    assert p_valid.shape == (2,)
    assert np.isfinite(delta).all() and np.isfinite(sigma).all() and np.isfinite(p_valid).all()


def test_empty_match_list_is_supported() -> None:
    model = SubpixelStereoRefiner().eval()
    empty_xy = np.empty((0, 2), dtype=np.float32)
    delta, sigma, p_valid = refine_matches(
        model,
        np.zeros((16, 16, 3), dtype=np.uint8),
        np.zeros((16, 16, 3), dtype=np.uint8),
        empty_xy,
        empty_xy,
        np.empty((0,), dtype=np.float32),
        torch.device("cpu"),
    )
    assert delta.shape == sigma.shape == (0, 2)
    assert p_valid.shape == (0,)
