# Result provenance

- Comparison: `raw_all` versus `refined_all`.
- Claim scope: rotation-only stereo extrinsic tracking.
- Frontend: frozen SuperPoint + LightGlue; all one-to-one matches retained.
- Refiner: selected seed-37 checkpoint at step 20,000.
- Tracker: full-Hessian rotation-only implementation using the TESO Gaussian
  epipolar-kernel objective; translation direction fixed to tooling.
- Split: 20 registered CARLA slow-drift validation sequences plus six control
  sequences.
- Statistical unit: sequence; 10,000 paired bootstrap repetitions.
- Overall artifact status: `FAIL` for the broader Gate C3, despite the positive
  rotation and vertical-residual comparison.
- Sealed test split: not accessed.

The machine-readable source of truth is `metrics.json`; `per_sequence.csv` and
`bootstrap.json` are included for audit.
