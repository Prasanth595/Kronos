import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from walk_forward_eval import (  # noqa: E402
    cone_coverage,
    directional_hit_rate,
    interpret,
    naive_mean_path_cone_width,
    pearson_ic,
    sample_quantile_cone_width,
    summarize_windows,
)
from model.kronos import aggregate_sample_paths


def test_aggregate_sample_paths_quantiles_are_across_samples_not_mean_bar():
    # Three paths that fan out on close (feature 3). Averaging first collapses them.
    samples = np.zeros((3, 4, 6), dtype=np.float64)
    samples[0, :, 3] = 10.0
    samples[1, :, 3] = 12.0
    samples[2, :, 3] = 14.0
    samples[:, :, 1] = samples[:, :, 3]  # high
    samples[:, :, 2] = samples[:, :, 3]  # low

    summary = aggregate_sample_paths(samples, quantile_levels=(0.1, 0.5, 0.9))
    np.testing.assert_allclose(summary["mean"][:, 3], 12.0)
    assert summary["q10"][0, 3] < summary["q50"][0, 3] < summary["q90"][0, 3]
    assert summary["q90"][0, 3] - summary["q10"][0, 3] > 2.0

    naive_width = naive_mean_path_cone_width(samples)
    sample_width = sample_quantile_cone_width(samples)
    assert naive_width == pytest.approx(0.0)
    assert sample_width > 2.0


def test_directional_hit_rate_and_ic():
    pred = np.array([0.01, -0.02, 0.03, -0.01])
    actual = np.array([0.02, -0.01, -0.04, -0.02])
    assert directional_hit_rate(pred, actual) == pytest.approx(0.75)
    assert pearson_ic(pred, pred) == pytest.approx(1.0)


def test_cone_coverage_and_summary_flags_no_edge():
    actual = np.array([10.0, 10.2, 9.8])
    assert cone_coverage(actual, np.array([9.5, 9.5, 9.5]), np.array([10.5, 10.5, 10.5])) == 1.0
    assert cone_coverage(actual, np.array([11.0, 11.0, 11.0]), np.array([12.0, 12.0, 12.0])) == 0.0

    rows = [
        {
            "kronos_return": 0.01,
            "actual_return": -0.02,
            "rw_return": 0.0,
            "kronos_mae": 0.4,
            "rw_mae": 0.2,
            "coverage": 0.3,
            "naive_cone_width": 0.01,
            "sample_cone_width": 0.2,
        },
        {
            "kronos_return": -0.01,
            "actual_return": 0.02,
            "rw_return": 0.0,
            "kronos_mae": 0.5,
            "rw_mae": 0.25,
            "coverage": 0.4,
            "naive_cone_width": 0.01,
            "sample_cone_width": 0.2,
        },
        {
            "kronos_return": 0.02,
            "actual_return": -0.01,
            "rw_return": 0.0,
            "kronos_mae": 0.3,
            "rw_mae": 0.15,
            "coverage": 0.2,
            "naive_cone_width": 0.01,
            "sample_cone_width": 0.2,
        },
    ]
    summary = summarize_windows(rows)
    assert summary["mae_ratio_vs_rw"] == pytest.approx(2.0)
    notes = " ".join(interpret(summary))
    assert "No point-forecast edge" in notes
    assert "No directional edge" in notes
    assert "mean-path high/low" in notes
    assert "RankIC" in notes
