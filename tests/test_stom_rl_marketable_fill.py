"""Unit tests for de-idealized marketable fills + rule-from-entry (Page P1b).

RULE strategy, NOT reinforcement learning.  Known-value checks: marketable buy
pays the ask and sell hits the bid (spread paid twice), TP/SL/time exits, the
entry cost, and entry from an arbitrary bar.  No DB / no I/O.
"""

from __future__ import annotations

import pytest

from stom_rl.marketable_fill import (
    EXIT_SL,
    EXIT_TIME,
    EXIT_TP,
    marketable_entry_price,
    marketable_exit_price,
    simulate_rule_from_entry,
)


def _approx(v, e, tol=1e-6):
    return abs(v - e) <= tol


def test_marketable_prices_cross_the_spread():
    assert _approx(marketable_entry_price(99.0, 101.0, 100.0), 101.0)  # buy pays ask
    assert _approx(marketable_exit_price(99.0, 101.0, 100.0), 99.0)    # sell hits bid
    # slippage on top
    assert _approx(marketable_entry_price(99.0, 101.0, 100.0, slippage_bps=100.0), 101.0 * 1.01)
    assert _approx(marketable_exit_price(99.0, 101.0, 100.0, slippage_bps=100.0), 99.0 * 0.99)


def test_marketable_prices_fall_back_to_price_when_quote_missing():
    assert _approx(marketable_entry_price(None, None, 100.0), 100.0)
    assert _approx(marketable_exit_price(None, None, 100.0), 100.0)
    assert _approx(marketable_entry_price(99.0, 0.0, 100.0), 100.0)  # non-positive ask -> price


def test_rule_from_entry_tp_no_spread():
    net, reason = simulate_rule_from_entry(
        [100.0, 110.0], [100.0, 110.0], [100.0, 110.0], [0, 1], 0,
        tp_pct=5.0, sl_pct=1.0, cost_bps=0.0,
    )
    assert reason == EXIT_TP
    assert _approx(net, 10.0)


def test_rule_from_entry_spread_eats_return():
    # entry fills at ask 101, exit hits bid 109 -> +7.92% (vs +10% mid move).
    net, reason = simulate_rule_from_entry(
        [100.0, 110.0], [99.0, 109.0], [101.0, 111.0], [0, 1], 0,
        tp_pct=5.0, sl_pct=1.0, cost_bps=0.0,
    )
    assert reason == EXIT_TP
    assert _approx(net, (109.0 / 101.0 - 1.0) * 100.0)  # ~7.921


def test_rule_from_entry_cost_subtracted():
    net, _ = simulate_rule_from_entry(
        [100.0, 110.0], [100.0, 110.0], [100.0, 110.0], [0, 1], 0,
        tp_pct=5.0, sl_pct=1.0, cost_bps=23.0,
    )
    assert _approx(net, 10.0 - 0.23)


def test_rule_from_entry_sl_and_time():
    sl_net, sl_r = simulate_rule_from_entry(
        [100.0, 98.0], [100.0, 98.0], [100.0, 98.0], [0, 1], 0,
        tp_pct=5.0, sl_pct=1.0, cost_bps=0.0,
    )
    assert sl_r == EXIT_SL and _approx(sl_net, -2.0)
    t_net, t_r = simulate_rule_from_entry(
        [100.0, 101.0, 102.0], [100.0, 101.0, 102.0], [100.0, 101.0, 102.0], [0, 1, 1500], 0,
        tp_pct=5.0, sl_pct=1.0, cost_bps=0.0,
    )
    assert t_r == EXIT_TIME and _approx(t_net, 2.0)


def test_rule_from_arbitrary_entry_index():
    # Enter at bar 1 (price 100), TP at +5% hit by bar 2 (110).
    net, reason = simulate_rule_from_entry(
        [100.0, 100.0, 110.0], [100.0, 100.0, 110.0], [100.0, 100.0, 110.0], [0, 1, 2], 1,
        tp_pct=5.0, sl_pct=1.0, cost_bps=0.0,
    )
    assert reason == EXIT_TP and _approx(net, 10.0)


def test_rule_from_entry_rejects_bad_inputs():
    with pytest.raises(ValueError):
        simulate_rule_from_entry([100.0], [100.0], [100.0], [0], 5)  # idx out of range
    with pytest.raises(ValueError):
        simulate_rule_from_entry([100.0, 101.0], [100.0, 101.0], [100.0, 101.0], [0, 1], 0, tp_pct=0.0)
    with pytest.raises(ValueError):
        marketable_entry_price(99.0, 101.0, 100.0, slippage_bps=-1.0)
