"""Unit tests for clean per-second liquidity reconstruction (experiment 2).

RULE strategy, NOT reinforcement learning.  Pure-function known-value checks for
the clean per-second flow, the auction-bar-excluded entry proxy, the cumulative
first-difference cross-check, and capacity summarisation (including that a clean
denominator yields HIGHER participation than the inflated one).  No DB / no I/O.
"""

from __future__ import annotations

import math

import pytest

from stom_rl.liquidity_recon import (
    clean_per_second_values,
    entry_liquidity_proxy,
    reconstruct_from_cumulative,
    summarize_capacity,
)


def _approx(v: float, e: float, tol: float = 1e-9) -> bool:
    return abs(v - e) <= tol


# ---------------------------------------------------------------------------
# clean_per_second_values
# ---------------------------------------------------------------------------
def test_clean_per_second_values_sums_buy_and_sell():
    out = clean_per_second_values([1_000_000, None, 0], [500_000, 2_000_000, None])
    assert out == [1_500_000.0, 2_000_000.0, 0.0]


def test_clean_per_second_values_length_mismatch_raises():
    with pytest.raises(ValueError):
        clean_per_second_values([1.0, 2.0], [1.0])


# ---------------------------------------------------------------------------
# entry_liquidity_proxy  (auction bar excluded; median of positive flow)
# ---------------------------------------------------------------------------
def test_entry_proxy_skips_first_and_medians_positive():
    # First value is the contaminated auction bar (huge); it must be skipped.
    psv = [999_999_999.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    # window after skipping index0: [10,20,30,40,50] -> median 30
    assert _approx(
        entry_liquidity_proxy(psv, window_bars=60, skip_first=True, min_bars=5), 30.0
    )


def test_entry_proxy_excludes_zeros_and_respects_min_bars():
    psv = [9e9, 0.0, 0.0, 10.0, 0.0, 20.0]  # only two positive after skip
    assert entry_liquidity_proxy(psv, min_bars=5) is None  # too thin
    assert _approx(entry_liquidity_proxy(psv, min_bars=2), 15.0)  # median(10,20)


def test_entry_proxy_window_truncation():
    psv = [9e9] + [100.0] * 3 + [1.0] * 100  # only first 3 continuous bars count
    # window_bars=3 after skip uses [100,100,100] -> median 100
    assert _approx(entry_liquidity_proxy(psv, window_bars=3, min_bars=3), 100.0)


def test_entry_proxy_rejects_bad_window():
    with pytest.raises(ValueError):
        entry_liquidity_proxy([1.0, 2.0], window_bars=0)


# ---------------------------------------------------------------------------
# reconstruct_from_cumulative  (positive first-difference; drops auction print)
# ---------------------------------------------------------------------------
def test_reconstruct_from_cumulative_differences():
    # cumulative won: auction 5_000_000 then +1M, +2M, (reset/dip -> 0), +3M
    cum = [5_000_000, 6_000_000, 8_000_000, 7_000_000, 10_000_000]
    out = reconstruct_from_cumulative(cum)
    assert out == [1_000_000.0, 2_000_000.0, 0.0, 3_000_000.0]


def test_reconstruct_handles_none():
    cum = [None, 1_000_000, None, 4_000_000]
    # diffs only across consecutive non-None: (1M -> None skipped) then 4M-1M=3M
    out = reconstruct_from_cumulative(cum)
    assert out == [3_000_000.0]


# ---------------------------------------------------------------------------
# summarize_capacity
# ---------------------------------------------------------------------------
def test_summarize_capacity_clean_denominator_known_values():
    # clean per-second values (won) for 4 instances.
    clean = [10_000_000, 5_000_000, 2_000_000, 1_000_000]
    cap = summarize_capacity(
        clean,
        accounts_won=[10_000_000],  # order = 0.1 * 10M = 1,000,000
        per_trade_fraction=0.10,
        base_cost_bps=23.0,
        gross_expectancy_pct=0.98,
        impact_coefs_bps=[10.0],
    )
    acct = cap["by_account"][0]
    # participations for order 1M: [0.1, 0.2, 0.5, 1.0] -> median 0.35
    assert _approx(acct["median_participation"], 0.35)
    assert _approx(acct["frac_feasible_le_1x"], 1.0)
    assert _approx(acct["frac_strict_le_0.1x"], 0.25)
    slip = acct["coef_sweep"][0]["median_slippage_bps"]
    assert _approx(slip, 10.0 * math.sqrt(0.35))
    # breakeven account where median order hits 1x of median clean value (3.5M):
    # median(clean)=3,500,000 ; /f=0.1 -> 35,000,000
    assert _approx(cap["median_clean_entry_value_won"], 3_500_000.0)
    assert _approx(cap["breakeven_1x_account_won_median"], 35_000_000.0)


def test_summarize_capacity_clean_raises_participation_vs_inflated():
    # Same order, but a CLEAN (smaller) denominator must give HIGHER participation
    # than an INFLATED one — the whole point of experiment 2.
    inflated = [100_000_000.0]  # contaminated, big
    clean = [2_000_000.0]       # clean, small
    order_acct = [10_000_000]   # order 1,000,000
    cap_inf = summarize_capacity(inflated, accounts_won=order_acct, impact_coefs_bps=[10.0])
    cap_cln = summarize_capacity(clean, accounts_won=order_acct, impact_coefs_bps=[10.0])
    assert (
        cap_cln["by_account"][0]["median_participation"]
        > cap_inf["by_account"][0]["median_participation"]
    )


def test_summarize_capacity_drops_non_positive():
    cap = summarize_capacity(
        [0.0, -5.0, None, 4_000_000.0], accounts_won=[10_000_000], impact_coefs_bps=[10.0]
    )
    assert cap["n_usable"] == 1 and cap["n_dropped"] == 3
