from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch

from calibmatch_teso.inference import refine_matches
from calibmatch_teso.refiner import SubpixelStereoRefiner


def read_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--matches", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-candidates", type=int, default=2048)
    parser.add_argument("--chunk", type=int, default=512)
    parser.add_argument("--backend", choices=("patch", "dense"), default="patch")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    stored = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model = SubpixelStereoRefiner().to(device)
    model.load_state_dict(stored["model"])
    model.eval()
    with np.load(args.matches, allow_pickle=False) as payload:
        left_xy = np.asarray(payload["left"], dtype=np.float64)
        right_xy = np.asarray(payload["right"], dtype=np.float64)
        score = np.asarray(payload["score"], dtype=np.float64)
    order = np.lexsort((np.arange(len(score)), -score))[: args.maximum_candidates]
    left_xy, right_xy, score = left_xy[order], right_xy[order], score[order]
    delta, sigma, p_valid = refine_matches(
        model,
        read_rgb(args.left),
        read_rgb(args.right),
        left_xy,
        right_xy,
        score,
        device,
        chunk=args.chunk,
        backend=args.backend,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        left=left_xy,
        right_initial=right_xy,
        right_refined=right_xy + delta,
        delta=delta,
        sigma=sigma,
        p_valid=p_valid,
        score=score,
        candidate_id=order,
    )


if __name__ == "__main__":
    main()

