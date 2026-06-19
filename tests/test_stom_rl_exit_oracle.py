"""Unit tests for the oracle-exit ceiling test (Page R1).

RULE strategy, NOT reinforcement learning.  These cover the pure regret core on
SYNTHETIC price paths.  The ceiling uses REALIZED fills on both legs (oracle and
rule), so regret is non-negative and measures pure exit-*timing* headroom; an
idealized-fill probe documents why that default is deliberate.  No DB is touched.
"""

from __future__ import annotations

import pytest

from stom_rl.gap_up_backtest import EXIT_SL, EXIT_TIME, EXIT_TP, GapUpInstance, simulate_trade
from stom_rl.exit_oracle import (
    exit_regret_pct,
    oracle_exit_net_pct,
    rule_exit_net_pct,
    summarize_exit_regret,
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
# Oracle: perfect-foresight best exit = max forward price, net of one cost.
# ---------------------------------------------------------------------------
def test_oracle_picks_max_forward_price():
    assert _approx(oracle_exit_net_pct([100.0, 105.0, 103.0], cost_bps=0.0), 5.0)
    assert _approx(oracle_exit_net_pct([100.0, 103.0, 108.0, 90.0], cost_bps=0.0), 8.0)


def test_oracle_no_forward_bar_exits_at_entry():
    # Only the entry bar -> the only achievable exit is the entry price -> 0% gross.
    assert _approx(oracle_exit_net_pct([100.0], cost_bps=0.0), 0.0)


def test_oracle_subtracts_one_round_trip_cost():
    # gross 10% minus 100bp (=1.0%) cost -> 9.0%.
    assert _approx(oracle_exit_net_pct([100.0, 110.0], cost_bps=100.0), 9.0)


def test_oracle_negative_when_path_only_falls():
    # All forward prices below entry: even the oracle loses (best of 99, 98).
    assert _approx(oracle_exit_net_pct([100.0, 99.0, 98.0], cost_bps=0.0), -1.0)


def test_oracle_rejects_bad_inputs():
    with pytest.raises(ValueError):
        oracle_exit_net_pct([], cost_bps=0.0)
    with pytest.raises(ValueError):
        oracle_exit_net_pct([0.0, 100.0], cost_bps=0.0)
    with pytest.raises(ValueError):
        oracle_exit_net_pct([100.0, 101.0], cost_bps=-1.0)


# ---------------------------------------------------------------------------
# Rule wrapper matches simulate_trade under the (default) realized fill.
# ---------------------------------------------------------------------------
def test_rule_exit_matches_simulate_trade_realized():
    # entry 100, TP5 level 105; bar to 106 fires TP, realized books actual 106.
    path = [100.0, 106.0, 90.0]
    got = rule_exit_net_pct(path, tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    expected = simulate_trade(
        path, tp_pct=5.0, sl_pct=1.0, cost_bps=0.0, fill_mode="realized"
    ).net_return_pct
    assert _approx(got, expected)
    assert _approx(got, 6.0)  # realized books the actual 106, not the 105 level


# ---------------------------------------------------------------------------
# Regret = oracle - rule, non-negative (realized), cost-invariant.
# ---------------------------------------------------------------------------
def test_regret_tp_sold_before_a_higher_print():
    # Rule sells at the first TP cross (106); oracle catches the later 112 -> 6.
    r = exit_regret_pct([100.0, 106.0, 112.0], tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    assert _approx(r, 6.0)


def test_regret_sl_cut_a_winner_that_recovered():
    # Rule stops out at the realized 98 (net -2); oracle catches the later 110 -> 12.
    r = exit_regret_pct([100.0, 98.0, 110.0], tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    assert _approx(r, 12.0)


def test_regret_zero_when_rule_already_optimal():
    # Peak (105) is exactly where the rule's TP books -> no headroom.
    r = exit_regret_pct([100.0, 105.0, 104.0], tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    assert _approx(r, 0.0)


def test_regret_is_non_negative_on_various_paths_realized():
    paths = [
        [100.0, 101.0, 99.5, 100.5],
        [100.0, 97.0, 96.0],
        [100.0, 120.0, 80.0],
        [100.0, 100.0],
    ]
    for p in paths:
        assert exit_regret_pct(p, tp_pct=5.0, sl_pct=1.0, cost_bps=23.0) >= -1e-9


def test_regret_is_cost_invariant():
    # Both oracle and rule pay one round-trip cost, so cost cancels in the regret.
    path = [100.0, 98.0, 107.0]  # SL then recovery -> regret 9 at any cost
    r0 = exit_regret_pct(path, tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    r23 = exit_regret_pct(path, tp_pct=5.0, sl_pct=1.0, cost_bps=23.0)
    r25 = exit_regret_pct(path, tp_pct=5.0, sl_pct=1.0, cost_bps=25.0)
    assert _approx(r0, 9.0)
    assert _approx(r0, r23)
    assert _approx(r0, r25)


def test_idealized_fill_can_make_regret_negative_documents_why_default_is_realized():
    # Gap-through stop: oracle (realized) books 97 (-3); idealized rule books the
    # SL LEVEL 99 (-1), an unattainable optimism -> regret = -3 - (-1) = -2 < 0.
    r_ideal = exit_regret_pct(
        [100.0, 97.0, 96.0], tp_pct=5.0, sl_pct=1.0, cost_bps=0.0, fill_mode="idealized"
    )
    assert r_ideal < 0.0
    # Realized fills fix it (rule books the realized 97 -> regret 0).
    r_real = exit_regret_pct(
        [100.0, 97.0, 96.0], tp_pct=5.0, sl_pct=1.0, cost_bps=0.0, fill_mode="realized"
    )
    assert _approx(r_real, 0.0)


# ---------------------------------------------------------------------------
# Summary aggregation incl. per-exit-reason breakdown (realized fills).
# ---------------------------------------------------------------------------
def test_summarize_empty_is_safe():
    s = summarize_exit_regret([])
    assert s["n"] == 0
    assert s["regret_mean_pct"] is None
    assert s["by_exit_reason"] == {}


def test_summarize_known_values_and_exit_reason_breakdown():
    # TP   : (100,106)        -> rule realized 106 +6 ; oracle 106  -> regret 0
    # SL   : (100,98,110)     -> rule realized  98 -2 ; oracle 110  -> regret 12
    # TIME : (100,101,100.5)  -> rule last   100.5 +.5; oracle 101  -> regret 0.5
    insts = [
        _inst("20230101", [100.0, 106.0]),
        _inst("20230102", [100.0, 98.0, 110.0]),
        _inst("20230103", [100.0, 101.0, 100.5]),
    ]
    s = summarize_exit_regret(insts, tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    assert s["n"] == 3
    assert _approx(s["regret_mean_pct"], (0.0 + 12.0 + 0.5) / 3, tol=1e-9)
    assert _approx(s["regret_median_pct"], 0.5)
    assert _approx(s["regret_max_pct"], 12.0)
    by = s["by_exit_reason"]
    assert by[EXIT_TP]["n"] == 1 and _approx(by[EXIT_TP]["regret_mean_pct"], 0.0)
    assert by[EXIT_SL]["n"] == 1 and _approx(by[EXIT_SL]["regret_mean_pct"], 12.0)
    assert by[EXIT_TIME]["n"] == 1 and _approx(by[EXIT_TIME]["regret_mean_pct"], 0.5)


def test_summarize_frac_rule_optimal():
    # One trade where the rule is already optimal (regret 0), one with headroom.
    insts = [
        _inst("20230101", [100.0, 105.0, 104.0]),  # regret 0 (rule optimal)
        _inst("20230102", [100.0, 98.0, 110.0]),   # regret 12 (SL cut a winner)
    ]
    s = summarize_exit_regret(insts, tp_pct=5.0, sl_pct=1.0, cost_bps=0.0)
    assert _approx(s["frac_rule_optimal"], 0.5)
