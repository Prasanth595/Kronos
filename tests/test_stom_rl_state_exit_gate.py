"""Unit tests for STOM 30s state-conditioned early-exit gate.

RULE / supervised risk-control, NOT reinforcement learning.  Synthetic-only
checks for paired accounting, train-only policy selection, primary-model GO
semantics, shuffled negative-control blocking, and checkpoint feature causality.
"""

from __future__ import annotations

import numpy as np

from stom_rl.state_exit_gate import (
    apply_negative_control_gate,
    checkpoint_features_from_rows,
    eligible_top_fraction_mask,
    run_state_exit_gate,
    score_exit_policy,
    select_exit_fraction,
    simulate_checkpoint_exit_pair,
    top_fraction_mask,
)


def _dates(n_dates: int) -> list[str]:
    return ["2023%02d%02d" % (1 + i // 28, 1 + i % 28) for i in range(n_dates)]


def _state_exit_dataset(
    *,
    seed: int,
    signal: float,
    n_symbols: int = 30,
    n_dates: int = 50,
    d: int = 6,
    base_mean: float = 0.0,
    noise: float = 0.05,
    all_eligible: bool = True,
):
    rng = np.random.default_rng(seed)
    X, baseline, early, eligible, dates, groups = [], [], [], [], [], []
    for dt in _dates(n_dates):
        for sym in range(n_symbols):
            x = rng.standard_normal(d)
            base = base_mean + rng.normal(0.0, noise)
            delta = signal * x[0] + rng.normal(0.0, noise)
            X.append(x)
            baseline.append(base)
            early.append(base + delta)
            eligible.append(all_eligible or (sym % 2 == 0))
            dates.append(dt)
            groups.append("s%03d_%s" % (sym, dt))
    return np.array(X), np.array(baseline), np.array(early), np.array(eligible, dtype=bool), dates, groups


def _rows(prices: list[float]) -> list[dict]:
    rows = []
    for sec, price in enumerate(prices):
        rows.append(
            {
                "sec": sec,
                "price": float(price),
                "cr": 2.5,
                "ts": 150.0 + sec,
                "buy_val": 1000.0 + sec,
                "sell_val": 900.0,
                "buy_qty": 10.0 + sec,
                "sell_qty": 9.0,
                "bid_tot": 600.0 + sec,
                "ask_tot": 400.0,
                "bid1": float(price) - 0.1,
                "ask1": float(price) + 0.1,
                "bidq1": 60.0,
                "askq1": 40.0,
            }
        )
    return rows


def test_top_fraction_mask_selects_stable_highest_scores():
    mask = top_fraction_mask([0.1, 0.9, 0.3, 0.8, 0.2], 0.4)
    assert mask.tolist() == [False, True, False, True, False]


def test_eligible_top_fraction_mask_maps_predictions_to_original_rows():
    mask = eligible_top_fraction_mask([0.1, 0.9, 0.3], [True, False, True, True], 1 / 3)
    assert mask.tolist() == [False, False, True, False]


def test_score_exit_policy_uses_all_original_trades_denominator():
    scored = score_exit_policy(
        baseline_net=[1.0, -1.0, 0.5, 2.0],
        early_exit_net=[0.0, 1.0, 10.0, -5.0],
        eligible_mask=[True, True, False, True],
        exit_mask=[True, True, True, False],
    )
    # Row 2 is ineligible, so even an exit_mask=True contributes zero increment.
    assert scored["n_original_trades"] == 4
    assert scored["n_checkpoint_eligible_trades"] == 3
    assert scored["n_policy_exits"] == 2
    assert scored["incremental_total_pct"] == 1.0  # (-1 -> 0) + (-1 -> 1)
    assert scored["incremental_mean_pct_per_original_trade"] == 0.25
    assert scored["eligible_incremental_mean_pct"] == 1.0 / 3.0


def test_select_exit_fraction_uses_train_delta_only():
    pred_train = np.array([0.9, 0.8, 0.7, 0.1])
    baseline = np.zeros(4)
    early = np.array([1.0, 1.0, -5.0, -5.0])
    selected = select_exit_fraction(pred_train, baseline, early, [True, True, True, True], (0.25, 0.5, 0.75))
    assert selected["selected_exit_fraction"] == 0.5


def test_state_exit_gate_go_on_planted_exit_edge_primary_gbm():
    X, baseline, early, eligible, dates, groups = _state_exit_dataset(seed=11, signal=2.0)
    res = run_state_exit_gate(
        X,
        baseline,
        early,
        eligible,
        dates,
        groups,
        n_bootstrap=200,
        rng_seed=11,
        n_trials=1,
        external_sharpe_variance=0.0,
        min_checkpoint_eligible_test=10,
        min_policy_exits=5,
    )
    assert res["primary_model_family"] == "gbm"
    assert res["verdict"] == "GO"
    assert res["models"]["gbm"]["go"] is True
    assert res["models"]["ridge"].get("diagnostic_only") is True
    assert res["models"]["ridge"].get("go") is False


def test_state_exit_gate_no_go_on_noise():
    X, baseline, _, eligible, dates, groups = _state_exit_dataset(seed=12, signal=0.0)
    rng = np.random.default_rng(120)
    early = baseline + rng.normal(0.0, 1.0, len(baseline))
    res = run_state_exit_gate(
        X,
        baseline,
        early,
        eligible,
        dates,
        groups,
        n_bootstrap=200,
        rng_seed=12,
        min_checkpoint_eligible_test=10,
        min_policy_exits=5,
    )
    assert res["verdict"] == "NO-GO"
    assert not any(m.get("go") for m in res["models"].values())


def test_state_exit_gate_inconclusive_when_primary_count_gate_fails():
    X, baseline, early, eligible, dates, groups = _state_exit_dataset(seed=13, signal=2.0, n_symbols=8)
    res = run_state_exit_gate(
        X,
        baseline,
        early,
        eligible,
        dates,
        groups,
        n_bootstrap=50,
        rng_seed=13,
        min_checkpoint_eligible_test=10_000,
        min_policy_exits=5,
    )
    assert res["verdict"] == "INCONCLUSIVE"
    assert res["inconclusive_reason"] == "primary_min_count_not_met"


def test_negative_controls_block_primary_go_unless_all_no_go():
    primary = {"verdict": "GO", "models": {"gbm": {"go": True}}}
    controls = [
        {"verdict": "NO-GO", "primary_model": {"go": False}},
        {"verdict": "GO", "primary_model": {"go": True}},
    ]
    gated = apply_negative_control_gate(primary, controls)
    assert gated["verdict_before_negative_control"] == "GO"
    assert gated["verdict"] == "NO-GO"
    assert gated["negative_control_passed"] is False
    assert gated["negative_control_blocked_go"] is True


def test_negative_controls_preserve_go_when_all_no_go():
    primary = {"verdict": "GO", "models": {"gbm": {"go": True}}}
    controls = [{"verdict": "NO-GO"} for _ in range(5)]
    gated = apply_negative_control_gate(primary, controls)
    assert gated["verdict"] == "GO"
    assert gated["negative_control_passed"] is True
    assert gated["negative_control_blocked_go"] is False


def test_simulate_checkpoint_exit_pair_zero_increment_when_closed_before_checkpoint():
    paired = simulate_checkpoint_exit_pair(
        prices=[100.0, 98.0, 97.0, 99.0],
        bids=[100.0, 98.0, 97.0, 99.0],
        asks=[100.0, 98.0, 97.0, 99.0],
        secs=[0, 10, 20, 30],
        checkpoint_sec=30,
        tp_pct=5.0,
        sl_pct=1.0,
        cost_bps=0.0,
    )
    assert paired["eligible"] is False
    assert paired["baseline_continue_net_pct"] == paired["early_exit_now_net_pct"]
    assert paired["delta_exit_now_pct"] == 0.0


def test_simulate_checkpoint_exit_pair_measures_checkpoint_exit_when_still_open():
    paired = simulate_checkpoint_exit_pair(
        prices=[100.0, 101.0, 102.0, 103.0, 104.0],
        bids=[100.0, 101.0, 102.0, 103.0, 104.0],
        asks=[100.0, 101.0, 102.0, 103.0, 104.0],
        secs=[0, 10, 20, 30, 1200],
        checkpoint_sec=30,
        tp_pct=5.0,
        sl_pct=5.0,
        cost_bps=0.0,
    )
    assert paired["eligible"] is True
    assert paired["checkpoint_sec_observed"] == 30
    assert abs(paired["early_exit_now_net_pct"] - 3.0) < 1e-9
    assert abs(paired["baseline_continue_net_pct"] - 4.0) < 1e-9
    assert abs(paired["delta_exit_now_pct"] + 1.0) < 1e-9


def test_checkpoint_features_ignore_rows_after_checkpoint():
    base = _rows([100.0] * 61)
    mutated = _rows([100.0] * 31 + [130.0] * 30)
    assert checkpoint_features_from_rows(base, checkpoint_sec=30) == checkpoint_features_from_rows(mutated, checkpoint_sec=30)
