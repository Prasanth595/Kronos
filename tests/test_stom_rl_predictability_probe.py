"""Unit tests for the predictability gate P0+P1 (pure stats, no DB).

RULE strategy, NOT reinforcement learning.  Covers MinTRL known values and the
walk-forward probe's discrimination: a PLANTED linear signal must yield GO (IC CI
> 0, net-of-cost DSR > 0.95) while pure NOISE must yield NO-GO (IC CI includes 0).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stom_rl.predictability_probe import min_track_record_length, run_probe


def _approx(value, expected, tol=1e-2):
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# P0 — MinTRL
# ---------------------------------------------------------------------------
def test_min_track_record_length_known_value():
    # SR=0.1, normal (kurt=3), prob .95:
    # num = 1 - 0 + (3-1)/4*0.1^2 = 1.005 ; (Z.95/0.1)^2 = (1.6448536/0.1)^2 = 270.554
    # MinTRL = 1 + 1.005*270.554 = 272.91
    assert _approx(min_track_record_length(0.1), 272.91, tol=0.05)


def test_min_track_record_length_infinite_when_not_above_benchmark():
    assert math.isinf(min_track_record_length(0.0))
    assert math.isinf(min_track_record_length(0.1, benchmark_sharpe=0.2))


def test_min_track_record_length_decreases_with_sharpe():
    assert min_track_record_length(0.2) < min_track_record_length(0.1)


# ---------------------------------------------------------------------------
# P1 — probe discrimination on synthetic data
# ---------------------------------------------------------------------------
def _dataset(signal: float, *, seed: int = 0, n_groups: int = 300, spg: int = 10,
             n_dates: int = 40, d: int = 6):
    rng = np.random.default_rng(seed)
    n = n_groups * spg
    X = rng.standard_normal((n, d))
    datepool = sorted("2023%02d%02d" % (1 + (i // 28), 1 + (i % 28)) for i in range(n_dates))
    gids, dts, secs = [], [], []
    for g in range(n_groups):
        dt = datepool[g % n_dates]
        for s in range(spg):
            gids.append("g%d" % g)
            dts.append(dt)
            secs.append(10.0 * (s + 1))
    noise = rng.standard_normal(n)
    y = (signal * X[:, 0] + 0.5 * noise) if signal > 0 else noise.copy()
    return X, y, dts, np.array(gids), np.array(secs, dtype=float)


def test_probe_detects_planted_signal_GO():
    X, y, dts, gids, secs = _dataset(signal=2.0, seed=1)
    res = run_probe(X, y, dts, gids, secs, n_bootstrap=200, rng_seed=1)
    ridge = res["models"]["ridge"]
    assert ridge["ic_primary"] > 0.3
    assert ridge["ic_ci_excludes_zero"] is True
    assert res["verdict"] == "GO"


def test_probe_rejects_pure_noise_NOGO():
    X, y, dts, gids, secs = _dataset(signal=0.0, seed=2)
    res = run_probe(X, y, dts, gids, secs, n_bootstrap=200, rng_seed=2)
    # No real signal -> IC CI should include zero for both models -> NO-GO.
    for name in ("ridge", "gbm"):
        lo, hi = res["models"][name]["ic_ci95"]
        assert lo <= 0.0 <= hi
    assert res["verdict"] == "NO-GO"


def test_probe_reports_structure():
    X, y, dts, gids, secs = _dataset(signal=1.0, seed=3)
    res = run_probe(X, y, dts, gids, secs, n_bootstrap=100, rng_seed=3)
    assert set(res["models"].keys()) == {"ridge", "gbm"}
    assert res["n_trials"] == 2 * 5
    assert res["verdict"] in {"GO", "NO-GO"}
    for d in res["per_boundary_ic"].values():
        assert len(d) == 5  # one IC per boundary
