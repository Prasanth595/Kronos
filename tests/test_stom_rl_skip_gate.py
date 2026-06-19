"""Unit tests for STOM experiment ① — entry skip-gate.

RULE strategy, NOT reinforcement learning.  These tests use synthetic arrays only
so they prove the accounting and controls before any DB/full-universe run.
"""

from __future__ import annotations

import numpy as np

from stom_rl.skip_gate import (
    apply_negative_control_gate,
    bottom_fraction_mask,
    run_skip_gate,
    score_skip_policy,
    select_skip_fraction,
)


def _dates(n_dates: int) -> list[str]:
    return ["2023%02d%02d" % (1 + i // 28, 1 + i % 28) for i in range(n_dates)]


def _dataset(
    *,
    seed: int,
    signal: float,
    n_symbols: int = 40,
    n_dates: int = 50,
    d: int = 6,
    positive_shift: float = 0.0,
):
    rng = np.random.default_rng(seed)
    X, net, dates, groups = [], [], [], []
    for dt in _dates(n_dates):
        for sym in range(n_symbols):
            x = rng.standard_normal(d)
            realized = positive_shift + signal * x[0] + rng.normal(0.0, 0.15)
            X.append(x)
            net.append(realized)
            dates.append(dt)
            groups.append("s%03d_%s" % (sym, dt))
    return np.array(X), np.array(net), dates, groups


def test_bottom_fraction_mask_skips_exact_rank_count():
    mask = bottom_fraction_mask([3.0, 1.0, 2.0, 0.0, 4.0], 0.4)
    assert mask.tolist() == [False, True, False, True, False]


def test_score_skip_policy_baseline_relative_accounting():
    scored = score_skip_policy([1.0, -2.0, 0.5], [False, True, False], ["a", "b", "c"])
    assert scored["baseline_total_net_pct"] == -0.5
    assert scored["policy_total_net_pct"] == 1.5
    assert scored["incremental_total_pct"] == 2.0
    assert scored["incremental_mean_pct"] == 2.0 / 3.0
    assert scored["skipped_net_mean_pct"] == -2.0
    assert scored["drift_trap_ok"] is True


def test_select_skip_fraction_uses_train_net_only():
    pred_train = np.array([0.0, 1.0, 2.0, 3.0])
    net_train = np.array([-5.0, -4.0, 3.0, 3.0])
    selected = select_skip_fraction(pred_train, net_train, (0.25, 0.5))
    assert selected["selected_skip_fraction"] == 0.5
    # A different test set would prefer 0.25, proving the selector itself is
    # train-local and not allowed to inspect test performance.
    pred_test = np.array([0.0, 1.0, 2.0, 3.0])
    net_test = np.array([-5.0, 4.0, 4.0, 4.0])
    assert select_skip_fraction(pred_test, net_test, (0.25, 0.5))["selected_skip_fraction"] == 0.25


def test_skip_gate_go_on_planted_money_losing_slice():
    X, net, dates, groups = _dataset(seed=1, signal=1.5)
    res = run_skip_gate(
        X,
        net,
        dates,
        groups,
        n_bootstrap=200,
        rng_seed=1,
        n_trials=1,
        external_sharpe_variance=0.0,
    )
    assert res["verdict"] == "GO"
    assert any(m.get("go") for m in res["models"].values())
    assert any(m.get("skipped_net_mean_pct") < 0 for m in res["models"].values())


def test_skip_gate_no_go_on_noise():
    X, _, dates, groups = _dataset(seed=2, signal=0.0)
    rng = np.random.default_rng(22)
    net = rng.normal(0.0, 1.0, len(dates))
    res = run_skip_gate(
        X,
        net,
        dates,
        groups,
        n_bootstrap=200,
        rng_seed=2,
    )
    assert res["verdict"] == "NO-GO"
    assert not any(m.get("go") for m in res["models"].values())


def test_skip_gate_blocks_drift_trap_when_skipped_net_is_positive():
    X, net, dates, groups = _dataset(seed=3, signal=0.05, positive_shift=0.75)
    res = run_skip_gate(
        X,
        net,
        dates,
        groups,
        n_bootstrap=200,
        rng_seed=3,
        n_trials=1,
        external_sharpe_variance=0.0,
    )
    assert res["verdict"] == "NO-GO"
    assert res["models"]
    assert all(m.get("drift_trap_ok") is False for m in res["models"].values())
    assert all((m.get("skipped_net_mean_pct") or 0.0) >= 0.0 for m in res["models"].values())


def test_skip_gate_reports_required_structure():
    X, net, dates, groups = _dataset(seed=4, signal=0.0)
    res = run_skip_gate(X, net, dates, groups, n_bootstrap=50, rng_seed=4)
    assert {
        "n_samples",
        "n_groups",
        "n_dates",
        "primary_boundary",
        "skip_fractions",
        "per_boundary_incremental_mean",
        "models",
        "symbol_disjoint",
        "verdict",
    }.issubset(res.keys())
    assert set(res["models"].keys()) == {"ridge", "gbm"}
    for model in res["models"].values():
        assert {
            "selected_skip_fraction",
            "incremental_mean_pct",
            "incremental_ci95",
            "incremental_dsr",
            "skipped_net_mean_pct",
            "policy_mean_net_pct",
            "baseline_mean_net_pct",
            "go",
        }.issubset(model.keys())


def test_negative_control_gate_blocks_primary_go():
    primary = {"verdict": "GO", "models": {"ridge": {"go": True}}}
    negative = {
        "verdict": "GO",
        "models": {"ridge": {"go": True, "incremental_mean_pct": 1.0, "skipped_net_mean_pct": -2.0}},
    }
    gated = apply_negative_control_gate(primary, negative)
    assert gated["verdict_before_negative_control"] == "GO"
    assert gated["verdict"] == "NO-GO"
    assert gated["negative_control_passed"] is False
    assert gated["negative_control_blocked_go"] is True
    assert gated["go_block_reason"] == "negative_control_not_no_go"


def test_negative_control_gate_preserves_go_when_control_no_go():
    primary = {"verdict": "GO", "models": {"ridge": {"go": True}}}
    negative = {"verdict": "NO-GO", "models": {"ridge": {"go": False}}}
    gated = apply_negative_control_gate(primary, negative)
    assert gated["verdict"] == "GO"
    assert gated["negative_control_passed"] is True
    assert gated["negative_control_blocked_go"] is False
