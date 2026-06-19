"""Unit tests for causal exit baselines + Deflated Sharpe toolkit (Page R1b).

RULE strategy, NOT reinforcement learning.  Covers the causal trailing-stop
simulator, per-trade Sharpe, the Bailey-Lopez de Prado expected-max-Sharpe and
Deflated Sharpe Ratio (known-value checks), and the grid / walk-forward
orchestration.  No DB is touched.
"""

from __future__ import annotations

import math

import pytest

from stom_rl.gap_up_backtest import EXIT_TIME, EXIT_TP, GapUpInstance
from stom_rl.exit_baselines import (
    EXIT_TRAIL,
    deflated_sharpe_ratio,
    default_candidate_grid,
    evaluate_exit_candidates,
    expected_max_sharpe,
    per_trade_sharpe,
    simulate_trailing_stop,
    walk_forward_select,
)


def _approx(value: float, expected: float, tol: float = 1e-9) -> bool:
    return abs(value - expected) <= tol


def _inst(session: str, prices, *, ts=150.0, imb=0.7) -> GapUpInstance:
    return GapUpInstance(
        symbol="SYM",
        session=session,
        entry_change_rate=2.5,
        entry_price=float(prices[0]),
        prices=tuple(float(p) for p in prices),
        seconds=tuple(32400 + i for i in range(len(prices))),
        entry_trade_strength=ts,
        entry_bid_ask_imbalance=imb,
    )


# ---------------------------------------------------------------------------
# Causal trailing stop.
# ---------------------------------------------------------------------------
def test_trailing_exits_on_pullback_from_peak():
    # peak 110, trail 2% -> stop 107.8; bar at 107 breaches -> realized books 107.
    r = simulate_trailing_stop([100.0, 110.0, 107.0], trail_pct=2.0, cost_bps=0.0)
    assert r.exit_reason == EXIT_TRAIL
    assert _approx(r.exit_price, 107.0)
    assert _approx(r.net_return_pct, 7.0)


def test_trailing_acts_as_initial_stop():
    # peak starts at entry 100 -> initial stop 99; bar at 98 stops out at 98.
    r = simulate_trailing_stop([100.0, 98.0], trail_pct=1.0, cost_bps=0.0)
    assert r.exit_reason == EXIT_TRAIL
    assert _approx(r.net_return_pct, -2.0)


def test_trailing_take_profit_checked_first():
    # TP5 level 105; bar to 106 fires TP (realized books 106) before any trail.
    r = simulate_trailing_stop(
        [100.0, 106.0, 90.0], trail_pct=5.0, tp_pct=5.0, cost_bps=0.0
    )
    assert r.exit_reason == EXIT_TP
    assert _approx(r.net_return_pct, 6.0)


def test_trailing_time_exit_when_never_stopped():
    # Monotone rise within 5% trail -> never stops -> time-exit at last bar 103.
    r = simulate_trailing_stop([100.0, 101.0, 102.0, 103.0], trail_pct=5.0, cost_bps=0.0)
    assert r.exit_reason == EXIT_TIME
    assert _approx(r.net_return_pct, 3.0)


def test_trailing_idealized_books_stop_level():
    # idealized books the stop LEVEL 107.8 (vs realized 107) on the same path.
    r = simulate_trailing_stop(
        [100.0, 110.0, 107.0], trail_pct=2.0, cost_bps=0.0, fill_mode="idealized"
    )
    assert r.exit_reason == EXIT_TRAIL
    assert _approx(r.net_return_pct, 7.8)


def test_trailing_rejects_bad_inputs():
    with pytest.raises(ValueError):
        simulate_trailing_stop([100.0, 99.0], trail_pct=0.0)
    with pytest.raises(ValueError):
        simulate_trailing_stop([], trail_pct=2.0)
    with pytest.raises(ValueError):
        simulate_trailing_stop([0.0, 99.0], trail_pct=2.0)
    with pytest.raises(ValueError):
        simulate_trailing_stop([100.0, 99.0], trail_pct=2.0, cost_bps=-1.0)
    with pytest.raises(ValueError):
        simulate_trailing_stop([100.0, 99.0], trail_pct=2.0, fill_mode="bogus")


# ---------------------------------------------------------------------------
# Per-trade Sharpe.
# ---------------------------------------------------------------------------
def test_per_trade_sharpe_known_value():
    # mean 2, sample stdev sqrt(2) -> sharpe = 2/sqrt(2) = sqrt(2).
    assert _approx(per_trade_sharpe([3.0, 1.0]), math.sqrt(2.0))


def test_per_trade_sharpe_undefined_cases():
    assert per_trade_sharpe([1.0]) is None  # < 2 samples
    assert per_trade_sharpe([5.0, 5.0]) is None  # zero variance


# ---------------------------------------------------------------------------
# Expected-max Sharpe (Bailey-Lopez de Prado).
# ---------------------------------------------------------------------------
def test_expected_max_sharpe_single_trial_is_zero():
    assert _approx(expected_max_sharpe(1, 1.0), 0.0)


def test_expected_max_sharpe_zero_variance_is_zero():
    assert _approx(expected_max_sharpe(50, 0.0), 0.0)


def test_expected_max_sharpe_increases_with_trials():
    assert expected_max_sharpe(2, 1.0) < expected_max_sharpe(10, 1.0)
    assert expected_max_sharpe(10, 1.0) < expected_max_sharpe(100, 1.0)


def test_expected_max_sharpe_scales_with_sqrt_variance():
    # sqrt(4)=2x the sqrt(1) case for the same trial count.
    assert _approx(
        expected_max_sharpe(20, 4.0), 2.0 * expected_max_sharpe(20, 1.0), tol=1e-9
    )


def test_expected_max_sharpe_rejects_bad_inputs():
    with pytest.raises(ValueError):
        expected_max_sharpe(0, 1.0)
    with pytest.raises(ValueError):
        expected_max_sharpe(10, -1.0)


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio.
# ---------------------------------------------------------------------------
def test_dsr_equals_half_at_the_expected_max_threshold():
    # observed == SR0 -> z = 0 -> DSR = 0.5 (exactly at the multiple-testing bar).
    sr0 = expected_max_sharpe(10, 1.0)
    dsr = deflated_sharpe_ratio(sr0, n_trials=10, sharpe_variance=1.0, n_samples=100)
    assert _approx(dsr, 0.5, tol=1e-9)


def test_dsr_monotonic_in_observed_sharpe():
    sr0 = expected_max_sharpe(10, 1.0)
    below = deflated_sharpe_ratio(sr0 - 0.2, n_trials=10, sharpe_variance=1.0, n_samples=100)
    above = deflated_sharpe_ratio(sr0 + 0.2, n_trials=10, sharpe_variance=1.0, n_samples=100)
    assert below < 0.5 < above


def test_dsr_high_for_strong_single_trial():
    dsr = deflated_sharpe_ratio(5.0, n_trials=1, sharpe_variance=0.0, n_samples=1000)
    assert dsr > 0.999


def test_dsr_fat_tails_lower_confidence():
    # Higher kurtosis inflates the denominator -> lower DSR for the same edge.
    base = deflated_sharpe_ratio(1.0, n_trials=1, sharpe_variance=0.0, n_samples=200, kurtosis=3.0)
    fat = deflated_sharpe_ratio(1.0, n_trials=1, sharpe_variance=0.0, n_samples=200, kurtosis=12.0)
    assert fat < base


def test_dsr_rejects_too_few_samples():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(1.0, n_trials=5, sharpe_variance=1.0, n_samples=1)


# ---------------------------------------------------------------------------
# Candidate grid evaluation + walk-forward selection.
# ---------------------------------------------------------------------------
def _mixed_instances():
    # A spread of TP / trail / recover / flat paths across 10 distinct dates so
    # net returns have variance (defined Sharpe) and the date split is non-empty.
    shapes = [
        [100.0, 106.0, 107.0],   # TP
        [100.0, 98.0, 97.0],     # down -> stop
        [100.0, 98.0, 110.0],    # dip then recover
        [100.0, 101.0, 100.5],   # flat-ish time exit
        [100.0, 108.0, 102.0],   # spike then fade
    ]
    return [
        _inst(f"202301{day:02d}", shapes[(day - 1) % len(shapes)])
        for day in range(1, 11)
    ]


def test_evaluate_exit_candidates_shapes_output():
    grid = [
        {"name": "fixed_tp5_sl1", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 1.0},
        {"name": "trail_2", "kind": "trail", "trail_pct": 2.0},
    ]
    res = evaluate_exit_candidates(_mixed_instances(), grid, cost_bps=23.0)
    assert {r["name"] for r in res} == {"fixed_tp5_sl1", "trail_2"}
    for r in res:
        assert r["n"] == 10
        assert r["mean_net_pct"] is not None
        assert r["win_rate"] is not None


def test_default_grid_has_baseline_first():
    grid = default_candidate_grid()
    assert grid[0]["name"] == "fixed_tp5_sl1"
    # Pin the trial count: DSR's deflation denominator depends on N = len(grid).
    assert len(grid) == 9
    # Baseline is fixed TP5/SL1; the grid widens SL and adds trailing variants.
    assert any(c["kind"] == "trail" for c in grid)
    assert any(c.get("sl_pct") == 3.0 for c in grid)


def test_evaluate_rejects_unsupported_fill_mode():
    grid = [{"name": "trail_2", "kind": "trail", "trail_pct": 2.0}]
    with pytest.raises(ValueError):
        evaluate_exit_candidates(
            [_inst("20230101", [100.0, 101.0])], grid, fill_mode="sl_gap_stress"
        )


def test_walk_forward_select_structure_and_dsr_range():
    grid = [
        {"name": "fixed_tp5_sl1", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 1.0},
        {"name": "fixed_tp5_sl2", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 2.0},
        {"name": "trail_2", "kind": "trail", "trail_pct": 2.0},
    ]
    wf = walk_forward_select(_mixed_instances(), grid, in_sample_fraction=0.7, cost_bps=23.0)
    assert wf["n_trials"] == 3
    assert wf["selected"] in {"fixed_tp5_sl1", "fixed_tp5_sl2", "trail_2"}
    assert wf["n_in_sample"] > 0 and wf["n_out_of_sample"] > 0
    # baseline OOS net is reported for the comparison.
    assert wf["baseline_oos_mean_net_pct"] is not None
    dsr = wf["deflated_sharpe_ratio"]
    assert dsr is None or (0.0 <= dsr <= 1.0)
