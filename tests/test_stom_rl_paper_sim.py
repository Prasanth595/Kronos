"""Unit tests for the frozen-policy paper replay (Page D).

RULE strategy, NOT reinforcement learning.  Synthetic chronological trade
sequences exercise: a single win's account math, the top-K concurrency cap, the
consecutive-loss halt at streak 7, the intraday daily-loss halt, compounding vs
fixed sizing, and max-drawdown tracking.  No DB / no I/O.
"""

from __future__ import annotations

import pytest

from stom_rl.gap_up_risk_sizing import RiskConfig
from stom_rl.paper_sim import simulate_paper_account


def _approx(value: float, expected: float, tol: float = 1e-3) -> bool:
    return abs(value - expected) <= tol


def _t(date: str, net_pct: float, *, strength: float = 150.0, sec=None):
    return {"date": date, "strength": strength, "sec_amount_won": sec, "net_pct": net_pct}


ONE_EOK = 100_000_000.0


def test_single_win_account_math():
    c = RiskConfig()
    s = simulate_paper_account([_t("20230102", 5.0)], c, initial_account_won=ONE_EOK)
    # order 0.10*1e8=1e7; +5% -> +500,000.
    assert _approx(s["final_account_won"], 100_500_000.0)
    assert _approx(s["total_return_pct"], 0.5)
    assert s["n_taken"] == 1 and s["n_signals"] == 1
    assert _approx(s["max_drawdown_pct"], 0.0)


def test_top_k_concurrency_cap():
    c = RiskConfig()  # K=3
    day = [_t("20230102", 1.0, strength=s) for s in (1, 2, 3, 4, 5)]
    s = simulate_paper_account(day, c, initial_account_won=ONE_EOK)
    # top-3 by strength taken; each +1% on 1e7 -> +100,000 x3.
    assert s["n_signals"] == 5
    assert s["n_taken"] == 3
    assert s["n_skipped_cap"] == 2
    assert _approx(s["final_account_won"], 100_300_000.0)


def test_consecutive_loss_halt_at_streak_7():
    c = RiskConfig()  # tiers halt (scale 0.0) at streak >= 7
    trades = [_t(f"202301{d:02d}", -1.0) for d in range(1, 9)]  # 8 losing days
    s = simulate_paper_account(trades, c, initial_account_won=ONE_EOK)
    # days 1-7 taken (streaks 0..6 -> f>0); day 8 (streak 7 -> f_eff 0) skipped.
    assert s["n_taken"] == 7
    assert s["n_skipped_halt"] == 1
    assert s["n_signals"] == 8


def test_streak_halt_is_a_recoverable_circuit_breaker_not_a_deadlock():
    c = RiskConfig()
    # 7 losing days build the streak to 7; day 8 (streak 7) trips the breaker and
    # is skipped + reset; day 9 (streak 0 again) must RESUME and take the win.
    trades = [_t(f"202301{d:02d}", -1.0) for d in range(1, 8)]  # 7 losses
    trades.append(_t("20230108", -1.0))  # day 8: halted (streak 7), then resets
    trades.append(_t("20230109", 5.0))   # day 9: resumes at full size, wins
    s = simulate_paper_account(trades, c, initial_account_won=ONE_EOK)
    assert s["n_taken"] == 8  # 7 losses + the day-9 win (NOT frozen forever)
    assert s["n_skipped_halt"] == 1  # only the day-8 halt day


def test_daily_loss_limit_halts_remaining_same_day_entries():
    # Tight 0.1% daily limit (=100,000 on 1e8); one -1.23% loss (-123,000) breaches it.
    c = RiskConfig(daily_loss_limit_pct=0.1)
    day = [_t("20230102", -1.23, strength=s) for s in (3, 2, 1)]
    s = simulate_paper_account(day, c, initial_account_won=ONE_EOK)
    assert s["n_taken"] == 1
    assert s["n_skipped_halt"] == 2
    assert s["n_days_daily_limit_hit"] == 1


def test_compounding_beats_fixed_after_gains():
    c = RiskConfig()
    wins = [_t("20230102", 5.0), _t("20230103", 5.0), _t("20230104", 5.0)]
    comp = simulate_paper_account(wins, c, initial_account_won=ONE_EOK, compounding=True)
    fixed = simulate_paper_account(wins, c, initial_account_won=ONE_EOK, compounding=False)
    assert comp["final_account_won"] > fixed["final_account_won"]
    assert fixed["final_account_won"] > ONE_EOK  # both profit on three wins


def test_max_drawdown_tracked_after_a_loss():
    c = RiskConfig()
    s = simulate_paper_account(
        [_t("20230102", 5.0), _t("20230103", -10.0)], c, initial_account_won=ONE_EOK
    )
    # peak 100.5M; then 0.10*100.5M=10.05M notional, -10% -> -1.005M -> 99.495M.
    # dd = 99.495/100.5 - 1 = -1.0%.
    assert _approx(s["max_drawdown_pct"], -1.0, tol=1e-2)


def test_empty_and_validation():
    c = RiskConfig()
    s = simulate_paper_account([], c, initial_account_won=ONE_EOK)
    assert s["n_signals"] == 0 and _approx(s["total_return_pct"], 0.0)
    assert _approx(s["final_account_won"], ONE_EOK)
    with pytest.raises(ValueError):
        simulate_paper_account([], c, initial_account_won=0.0)


def test_liquidity_cap_shrinks_sizing():
    # A thin name (sec_amount 1,000,000원 << base order) caps the order via
    # position_notional_won -> notional = max_participation * 1,000,000.
    c = RiskConfig(max_participation=1.0)  # explicit: cap = 1.0 * sec_amount
    s = simulate_paper_account(
        [_t("20230102", 5.0, sec=1_000_000.0)], c, initial_account_won=ONE_EOK
    )
    # capped order 1,000,000; +5% -> +50,000 (vs +500,000 uncapped).
    assert _approx(s["final_account_won"], 100_050_000.0)
