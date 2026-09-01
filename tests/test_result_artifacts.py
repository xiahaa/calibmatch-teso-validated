from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


def test_per_sequence_csv_recomputes_published_means() -> None:
    result_dir = (
        Path(__file__).resolve().parents[1]
        / "results"
        / "raw_all_vs_refined_all"
    )
    metrics = json.loads((result_dir / "metrics.json").read_text(encoding="utf-8"))
    with (result_dir / "per_sequence.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    slow = [row for row in rows if row["kind"] == "slow"]
    control = [row for row in rows if row["kind"] == "control"]
    assert len(slow) == metrics["slow_sequence_count"] == 20
    assert len(control) == metrics["control_sequence_count"] == 6

    fields = {
        "rotation": ("baseline_rotation_deg", "candidate_rotation_deg"),
        "translation": ("baseline_translation_deg", "candidate_translation_deg"),
        "vertical": ("baseline_vertical_p95_px", "candidate_vertical_p95_px"),
    }
    for name, (baseline_field, candidate_field) in fields.items():
        expected = metrics["comparisons"][name]
        baseline = np.asarray([float(row[baseline_field]) for row in slow])
        candidate = np.asarray([float(row[candidate_field]) for row in slow])
        np.testing.assert_allclose(baseline.mean(), expected["baseline_mean"], rtol=0, atol=1e-12)
        np.testing.assert_allclose(candidate.mean(), expected["candidate_mean"], rtol=0, atol=1e-12)
        np.testing.assert_allclose(
            (baseline - candidate).mean(), expected["mean_difference"], rtol=0, atol=1e-12
        )

    control_baseline = np.asarray([float(row["baseline_rotation_deg"]) for row in control])
    control_candidate = np.asarray([float(row["candidate_rotation_deg"]) for row in control])
    np.testing.assert_allclose(
        control_baseline.mean(), metrics["control_rotation"]["baseline_mean"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        control_candidate.mean(), metrics["control_rotation"]["candidate_mean"], rtol=0, atol=1e-12
    )
