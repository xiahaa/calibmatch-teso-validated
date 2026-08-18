# CalibMatch-TESO: validated endpoint-refinement snapshot

This repository is a compact, integrity-preserving snapshot of the one result
that remained supported after the larger CalibMatch research project was
paused:

> Subpixel refinement of frozen LightGlue right endpoints improves a
> rotation-only, TESO-kernel stereo extrinsic tracker when all one-to-one
> matches are retained.

On 20 registered CARLA validation sequences, the fixed seed-37 comparison
`raw_all -> refined_all` produced:

| Metric | Raw LightGlue | Refined endpoints | Relative change |
|---|---:|---:|---:|
| Rotation error | 0.041270 deg | 0.023424 deg | -43.24% |
| Vertical p95 | 0.223356 px | 0.163189 px | -26.94% |

Both metrics improved on 20/20 sequences and their paired sequence-bootstrap
95% confidence intervals excluded zero. The exact aggregate artifacts are in
`results/raw_all_vs_refined_all/`.

## Scope warning

This is a **partial positive result**, not a paper-ready method release. The
larger pre-registered project did not retain a 5-DoF translation-direction
claim, did not pass its downstream-depth threshold, and found no additional
material benefit from learned calibration-influence supervision, selection,
or direct differentiable TESO supervision. Those failed routes are
intentionally excluded from the executable snapshot rather than hidden:
`results/RESEARCH_BOUNDARY.md` records the negative conclusions. The aggregate
has `status: FAIL` because the broader pre-registered Gate C3 did not pass. The
sealed test split was never accessed.

## Included

- the `33x33` patch-based subpixel endpoint refiner;
- patch and dense-feature inference backends;
- a full-Hessian rotation-only tracker using TESO's Gaussian epipolar kernel;
- selected checkpoints for seeds 13, 37, and 73;
- unit tests and aggregate validation evidence.

The included checkpoints were trained with the archived composite
calibration-influence objective. A matched attribution experiment found only a
1.97% rotation gain over EPE/BCE training and worse no-drift behavior, so that
objective is **not** claimed as a supported contribution. This repository is
an inference/evaluation snapshot; it does not claim to reproduce checkpoint
training. Exact provenance and hashes are in `MODEL_CARD.md` and
`checkpoints/SHA256SUMS`.

## Not included

- CARLA images, dense GT, LightGlue caches, or sealed manifests;
- LightGlue, TESO, EfficientLoFTR, or other external weights/code;
- D-optimal selection, learned calibration-influence scoring, 5-DoF recovery,
  differentiable TESO loss, or downstream depth experiments.

## Installation

Python 3.10 and PyTorch 2.4.1 were used for the recorded experiments. Install a
CUDA-compatible PyTorch build separately, then:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Minimal inference

Refine an existing LightGlue match file containing `left`, `right`, and
`score` arrays:

```bash
python scripts/refine_lightglue_matches.py \
  --left left.png --right right.png \
  --matches matches.npz \
  --checkpoint checkpoints/seed37_step20000.pt \
  --output refined_matches.npz
```

The output contains the original endpoints, predicted offsets, refined right
endpoints, coordinate scales, and validity probabilities.

## External attribution

The tracker objective follows TESO, pinned in the original experiments at
commit `a309db1f5e5c15ac38e2cf8036f441787be33327`. LightGlue proposals were
generated at commit `eb42fee2d71449efb0aa5c10549752b5d75384d8`.
No source code from either project is vendored here. See `NOTICE.md`.

## License

No reuse license has been selected for this snapshot yet. The repository owner
should choose a license compatible with the intended public/private release
and the TESO attribution obligations before making the repository public.
