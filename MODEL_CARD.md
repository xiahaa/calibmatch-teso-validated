# Model card

## Intended use

The three checkpoints refine the right endpoint of frozen LightGlue stereo
matches. Their validated use is an all-match, rotation-only tracker with fixed
tooling translation direction. They are research artifacts, not a complete
online calibration system.

## Checkpoint selection and provenance

The checkpoints came from the archived formal training run
`formal_pipeline_v1_bc308d4`:

| Seed | Selected step | SHA-256 |
|---:|---:|---|
| 13 | 25,000 | `5cce2edf9aa1bf27e718498fb9ebe5fc895ca424e7e8061dca0b37a43b312b07` |
| 37 | 20,000 | `0a3b917df73a37d66eb87d261bd5fee126f8a221f98956bd32b7beb5a86d4875` |
| 73 | 30,000 | `f49ac887c2156d38d5c2d569a225792b81fda66354ce7ac86f6a9ac8f2211815` |

The archived training configuration used a composite objective with Laplace
endpoint refinement, validity BCE, a differentiable 5-DoF update surrogate,
and coverage terms. Later matched attribution showed that the
calibration-influence component improved rotation by only 1.97% over EPE/BCE
training and worsened no-drift control. It is therefore not presented as a
validated contribution, and the simplified training program that could not
reproduce these checkpoints is deliberately excluded.

## Validation evidence

The released `raw_all_vs_refined_all` aggregate used the selected seed-37
checkpoint on 20 registered CARLA validation sequences. Compared with raw
LightGlue endpoints, refinement reduced sequence-mean rotation error by 43.24%
and dense vertical p95 by 26.94%; both improved on 20/20 sequences and their
paired sequence-bootstrap 95% confidence intervals excluded zero.

The artifact as a whole is marked `FAIL`: it did not establish 5-DoF recovery,
did not meet the downstream-depth target, ran at 9.87 Hz rather than the
pre-registered 10 Hz target, and never accessed the sealed test split. These
checkpoints must not be described as a paper-ready or test-confirmed method.

## Limitations

- CARLA validation only; no sealed test or real-rig confirmation.
- Translation direction is fixed rather than estimated.
- The positive result does not isolate the training objective as causal.
- LightGlue and TESO are external dependencies and are not bundled.
- No commercial or safety-critical use is supported.
