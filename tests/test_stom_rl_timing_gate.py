"""Unit tests for the P1b baseline-relative de-idealized timing gate (pure stats).

RULE strategy, NOT reinforcement learning.  A PLANTED per-session timing signal
(a feature that ranks which decision second has the higher entry-net) must yield
GO (incremental-vs-rule CI > 0, DSR > 0.95); pure noise must yield NO-GO (the
model's pick is no better than the rule baseline).  No DB / no I/O.
"""

from __future__ import annotations

import numpy as np

from stom_rl.timing_gate import run_timing_gate


def _ds(signal: float, *, seed: int = 0, n_groups: int = 300, spg: int = 10,
        n_dates: int = 40, d: int = 6):
    rng = np.random.default_rng(seed)
    n = n_groups * spg
    X = rng.standard_normal((n, d))
    datepool = sorted("2023%02d%02d" % (1 + (i // 28), 1 + (i % 28)) for i in range(n_dates))
    gids, dts, secs, base = [], [], [], []
    for g in range(n_groups):
        dt = datepool[g % n_dates]
        for s in range(spg):
            gids.append("g%d" % g)
            dts.append(dt)
            secs.append(10.0 * (s + 1))
            base.append(0.0)  # rule fixed-entry baseline net = 0 for all sessions
    noise = rng.standard_normal(n)
    # entry-net y: varies with feature 0 when signal>0 (so picking high-X0 second
    # beats the baseline); pure noise (mean 0 = baseline) when signal==0.
    y = (signal * X[:, 0] + 0.1 * noise) if signal > 0 else noise.copy()
    return X, y, dts, np.array(gids), np.array(secs, dtype=float), np.array(base, dtype=float)


def test_timing_gate_GO_on_planted_timing_signal():
    X, y, dts, gids, secs, base = _ds(signal=1.0, seed=1)
    res = run_timing_gate(X, y, dts, gids, secs, base, n_bootstrap=200, rng_seed=1)
    # The model should pick higher-net entries than the rule -> positive increment.
    assert res["verdict"] == "GO"
    m = res["models"]["ridge"]
    assert m["incremental_mean_pct"] > 0.0
    assert m["ci_excludes_zero"] is True
    assert m["dsr_gt_0_95"] is True


def test_timing_gate_NOGO_on_noise():
    X, y, dts, gids, secs, base = _ds(signal=0.0, seed=2)
    res = run_timing_gate(X, y, dts, gids, secs, base, n_bootstrap=200, rng_seed=2)
    # No predictable timing edge -> model pick no better than baseline -> CI spans 0.
    for name in ("ridge", "gbm"):
        lo, hi = res["models"][name]["incremental_ci95"]
        assert lo <= 0.0 <= hi
    assert res["verdict"] == "NO-GO"


def test_timing_gate_reports_structure():
    X, y, dts, gids, secs, base = _ds(signal=0.5, seed=3)
    res = run_timing_gate(X, y, dts, gids, secs, base, n_bootstrap=100, rng_seed=3)
    assert set(res["models"].keys()) == {"ridge", "gbm"}
    assert res["verdict"] in {"GO", "NO-GO"}
    assert res["n_trials"] >= 1
    for dd in res["per_boundary_incremental_mean"].values():
        assert len(dd) == 5
