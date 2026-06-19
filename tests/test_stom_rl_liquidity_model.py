"""Unit tests for the liquidity feasibility & slippage model (Page C).

RULE strategy, NOT reinforcement learning.  Pure-function known-value checks for
participation rate, feasibility, square-root slippage, slippage-adjusted
expectancy, the slippage-budget order cap, and the per-trade liquidity summary
(including non-positive entry_sec_amount dropping).  No DB / no I/O.
"""

from __future__ import annotations

import math

import pytest

from stom_rl.liquidity_model import (
    _load_entry_sec_amounts,
    is_liquidity_feasible,
    max_order_for_slippage_budget_won,
    participation_rate,
    slippage_adjusted_expectancy_pct,
    sqrt_impact_slippage_bps,
    summarize_liquidity,
)


def _approx(value: float, expected: float, tol: float = 1e-9) -> bool:
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# participation_rate / feasibility
# ---------------------------------------------------------------------------
def test_participation_rate_known():
    assert _approx(participation_rate(1_000_000, 5_000_000), 0.2)
    assert _approx(participation_rate(0, 5_000_000), 0.0)


def test_participation_rate_rejects_bad_inputs():
    with pytest.raises(ValueError):
        participation_rate(-1, 5_000_000)
    with pytest.raises(ValueError):
        participation_rate(1_000_000, 0)


def test_is_liquidity_feasible_boundary_inclusive():
    assert is_liquidity_feasible(1_000_000, 5_000_000, max_participation=0.5) is True
    assert is_liquidity_feasible(3_000_000, 5_000_000, max_participation=0.5) is False
    # boundary: participation == max_participation is feasible (<=).
    assert is_liquidity_feasible(2_500_000, 5_000_000, max_participation=0.5) is True
    with pytest.raises(ValueError):
        is_liquidity_feasible(1_000_000, 5_000_000, max_participation=0.0)


# ---------------------------------------------------------------------------
# square-root slippage + adjusted expectancy
# ---------------------------------------------------------------------------
def test_sqrt_impact_slippage_known():
    # coef 10, participation 0.25 -> 10 * sqrt(0.25) = 10 * 0.5 = 5 bp.
    assert _approx(sqrt_impact_slippage_bps(0.25, impact_coef_bps=10.0), 5.0)
    assert _approx(sqrt_impact_slippage_bps(0.0, impact_coef_bps=10.0), 0.0)


def test_sqrt_impact_rejects_bad_inputs():
    with pytest.raises(ValueError):
        sqrt_impact_slippage_bps(-0.1, impact_coef_bps=10.0)
    with pytest.raises(ValueError):
        sqrt_impact_slippage_bps(0.25, impact_coef_bps=-1.0)


def test_slippage_adjusted_expectancy_known():
    # gross 0.98%, base 23bp + slip 5bp = 28bp = 0.28% -> 0.70%.
    assert _approx(slippage_adjusted_expectancy_pct(0.98, 23.0, 5.0), 0.70)


def test_slippage_adjusted_rejects_negative_costs():
    with pytest.raises(ValueError):
        slippage_adjusted_expectancy_pct(0.98, -1.0, 5.0)
    with pytest.raises(ValueError):
        slippage_adjusted_expectancy_pct(0.98, 23.0, -1.0)


# ---------------------------------------------------------------------------
# slippage-budget order cap (inverse of sqrt impact)
# ---------------------------------------------------------------------------
def test_max_order_for_budget_equals_sec_amount_when_budget_equals_coef():
    # budget == coef -> p_max = 1 -> order_max = entry_sec_amount.
    assert _approx(
        max_order_for_slippage_budget_won(10_000_000, slippage_budget_bps=10.0, impact_coef_bps=10.0),
        10_000_000.0,
    )


def test_max_order_for_budget_squares_the_ratio():
    # budget 50, coef 10 -> p_max = 25 -> order = 250,000,000.
    assert _approx(
        max_order_for_slippage_budget_won(10_000_000, slippage_budget_bps=50.0, impact_coef_bps=10.0),
        250_000_000.0,
    )


def test_max_order_rejects_bad_inputs():
    with pytest.raises(ValueError):
        max_order_for_slippage_budget_won(10_000_000, slippage_budget_bps=-1.0)
    with pytest.raises(ValueError):
        max_order_for_slippage_budget_won(10_000_000, slippage_budget_bps=10.0, impact_coef_bps=0.0)
    with pytest.raises(ValueError):
        max_order_for_slippage_budget_won(0, slippage_budget_bps=10.0)


# ---------------------------------------------------------------------------
# summarize_liquidity
# ---------------------------------------------------------------------------
def test_summarize_liquidity_known_values():
    # order 1,000,000 over sec_amounts -> participations [0.1,0.2,0.5,1.0].
    sec = [10_000_000, 5_000_000, 2_000_000, 1_000_000]
    s = summarize_liquidity(
        sec, order_won=1_000_000, base_cost_bps=23.0, gross_expectancy_pct=0.98,
        impact_coef_bps=10.0,
    )
    assert s["n"] == 4 and s["n_dropped"] == 0
    assert _approx(s["median_participation"], 0.35)  # mean(0.2, 0.5)
    assert _approx(s["frac_feasible"], 1.0)  # all <= 1x
    assert _approx(s["frac_strict"], 0.25)  # only 0.1 <= 0.1x
    assert _approx(s["median_slippage_bps"], 10.0 * math.sqrt(0.35))
    assert _approx(
        s["slippage_adj_expectancy_pct_at_median"],
        0.98 - (23.0 + 10.0 * math.sqrt(0.35)) / 100.0,
    )


def test_summarize_liquidity_drops_non_positive_sec_amount():
    s = summarize_liquidity(
        [None, 0, -5, 10_000_000], order_won=1_000_000, impact_coef_bps=10.0
    )
    assert s["n"] == 1 and s["n_dropped"] == 3
    assert _approx(s["median_participation"], 0.1)


def test_summarize_liquidity_empty_is_safe():
    s = summarize_liquidity([], order_won=1_000_000)
    assert s["n"] == 0
    assert s["median_participation"] is None
    assert s["slippage_adj_expectancy_pct_at_median"] is None


def test_load_entry_sec_amounts_scales_and_filters(tmp_path):
    # 초당거래대금 stored in 백만원 -> loader converts to won (x1e6); ts_imb filter;
    # None dropped.
    import json

    p = tmp_path / "inst.json"
    p.write_text(
        json.dumps(
            [
                {"pass_ts_imb": True, "entry_sec_amount": 622.0},
                {"pass_ts_imb": False, "entry_sec_amount": 100.0},  # filtered (not ts_imb)
                {"pass_ts_imb": True, "entry_sec_amount": None},     # dropped (None)
                {"pass_ts_imb": True, "entry_sec_amount": 2.0},
            ]
        ),
        encoding="utf-8",
    )
    vals = _load_entry_sec_amounts(str(p), only_ts_imb=True, unit_won=1_000_000.0)
    assert vals == [622_000_000.0, 2_000_000.0]


def test_summarize_liquidity_larger_account_raises_participation():
    sec = [10_000_000, 5_000_000, 2_000_000, 1_000_000]
    small = summarize_liquidity(sec, order_won=1_000_000)
    big = summarize_liquidity(sec, order_won=10_000_000)
    # 10x the order -> 10x the participation, so feasibility can only drop.
    assert big["median_participation"] > small["median_participation"]
    assert big["frac_feasible"] <= small["frac_feasible"]
