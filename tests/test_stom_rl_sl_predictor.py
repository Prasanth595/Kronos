"""Unit tests for experiment 3 — SL-predictability precursor gate.

RULE strategy, NOT reinforcement learning.  Pure-function checks: the rule exit
reason (tp/sl/time + SL-on-tie), and the gate's verdicts on a PLANTED separable
SL signal (must be PREDICTABLE) vs pure noise (must be AT-CHANCE).  No DB / no I/O.
"""

from __future__ import annotations

import numpy as np
import pytest

from stom_rl.sl_predictor import rule_exit_reason, run_sl_gate


# ---------------------------------------------------------------------------
# rule_exit_reason
# ---------------------------------------------------------------------------
def test_exit_reason_tp():
    reason, idx = rule_exit_reason([100.0, 102.0, 105.0], [0, 1, 2], tp_pct=5.0, sl_pct=1.0)
    assert reason == "tp" and idx == 2


def test_exit_reason_sl():
    reason, idx = rule_exit_reason([100.0, 100.5, 99.0], [0, 1, 2], tp_pct=5.0, sl_pct=1.0)
    assert reason == "sl" and idx == 2


def test_exit_reason_time():
    reason, idx = rule_exit_reason([100.0, 100.5, 101.0], [0, 1, 2], tp_pct=5.0, sl_pct=1.0)
    assert reason == "time" and idx == 2


def test_exit_reason_sl_wins_on_first_breach_order():
    # SL is checked before TP per scan step; a bar at exactly -1% stops out.
    reason, idx = rule_exit_reason([100.0, 99.0], [0, 1], tp_pct=5.0, sl_pct=1.0)
    assert reason == "sl" and idx == 1


def test_exit_reason_rejects_bad_inputs():
    with pytest.raises(ValueError):
        rule_exit_reason([], [])
    with pytest.raises(ValueError):
        rule_exit_reason([0.0, 1.0], [0, 1])


# ---------------------------------------------------------------------------
# run_sl_gate — planted signal vs noise
# ---------------------------------------------------------------------------
def _dataset(signal: float, *, seed: int, n_symbols: int = 60, n_dates: int = 40, d: int = 6):
    """Synthetic dataset mirroring real shape: each of ``n_symbols`` tickers appears
    across many dates (so the symbol-disjoint 70/30 split has both classes)."""

    rng = np.random.default_rng(seed)
    datepool = sorted("2023%02d%02d" % (1 + i // 28, 1 + i % 28) for i in range(n_dates))
    X, y, dates, groups = [], [], [], []
    for di, dt in enumerate(datepool):
        for sym in range(n_symbols):
            x = rng.standard_normal(d)
            prob = 1.0 / (1.0 + np.exp(-signal * x[0])) if signal > 0 else 0.5
            label = int(rng.random() < prob)
            X.append(x)
            y.append(label)
            dates.append(dt)
            groups.append("s%03d_%s" % (sym, dt))
    return np.array(X), np.array(y), dates, groups


def test_sl_gate_predictable_on_planted_signal():
    X, y, dates, groups = _dataset(signal=3.0, seed=1)
    res = run_sl_gate(X, y, dates, groups, n_bootstrap=200, rng_seed=1)
    assert res["verdict"] == "PREDICTABLE"
    assert res["predictable"] is True
    # at least one model clears all three bars
    assert any(m.get("predictable") for m in res["walk_forward"]["models"].values())


def test_sl_gate_at_chance_on_noise():
    X, y, dates, groups = _dataset(signal=0.0, seed=2)
    res = run_sl_gate(X, y, dates, groups, n_bootstrap=200, rng_seed=2)
    assert res["verdict"] == "AT-CHANCE"
    assert res["predictable"] is False


def test_sl_gate_reports_structure():
    X, y, dates, groups = _dataset(signal=0.0, seed=3)
    res = run_sl_gate(X, y, dates, groups, n_bootstrap=100, rng_seed=3)
    assert set(("n_samples", "base_rate_sl", "walk_forward", "symbol_disjoint_auc",
                "predictable", "verdict")).issubset(res.keys())
    assert 0.0 <= res["base_rate_sl"] <= 1.0
    assert res["thresholds"]["auc_meaningful"] == 0.55
