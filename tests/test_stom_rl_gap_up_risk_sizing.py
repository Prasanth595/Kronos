"""Unit tests for gap-up RULE-strategy position sizing & risk control.

RULE strategy, NOT reinforcement learning.  These cover the pure sizing/risk
functions on KNOWN values (no DB, no I/O): per-trade notional + liquidity cap,
1R, the daily loss limit & halt, concurrency exposure, consecutive-loss + monthly
de-risking, account-MDD translation, degenerate Kelly, and the per-account plan
bundle that backs the Page A doc's worked-example table.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from stom_rl.gap_up_risk_sizing import (
    DEFAULT_CONSECUTIVE_LOSS_TIERS,
    DEFAULT_COST_BPS,
    DEFAULT_SL_PCT,
    DEFAULT_TP_PCT,
    IDEALIZED_EXPECTANCY_PCT,
    MAX_LOSS_STREAK,
    PRIMARY_FILTER,
    STRATEGY_MDD_IDEALIZED_PCT,
    STRATEGY_MDD_STRESS_PCT,
    STRESS_EXPECTANCY_PCT,
    RiskConfig,
    account_mdd_estimate_pct,
    consecutive_loss_scale,
    daily_limit_in_r,
    daily_loss_limit_won,
    effective_fraction,
    expected_pnl_won,
    full_kelly_fraction,
    max_concurrent_exposure_pct,
    max_concurrent_exposure_won,
    plan_for_account,
    position_notional_won,
    risk_per_trade_won,
    risk_unit_account_pct,
    should_halt_day,
    worst_case_concurrent_loss_won,
)

# Account sizes from the Page A doc's worked-example table.
ONE_CHEON = 10_000_000  # 1,000만원
FIVE_CHEON = 50_000_000  # 5,000만원
ONE_EOK = 100_000_000  # 1억원


def _approx(value: float, expected: float, tol: float = 1e-6) -> bool:
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# Locked descriptive constants (RULE strategy, ts_imb @ 23bp).
# ---------------------------------------------------------------------------
def test_locked_strategy_constants():
    assert PRIMARY_FILTER == "ts_imb"  # RULE filter, NOT an RL policy
    assert DEFAULT_TP_PCT == 5.0
    assert DEFAULT_SL_PCT == 1.0
    assert DEFAULT_COST_BPS == 23.0
    assert _approx(IDEALIZED_EXPECTANCY_PCT, 0.952)
    assert _approx(STRESS_EXPECTANCY_PCT, 0.811)
    assert MAX_LOSS_STREAK == 9
    assert STRATEGY_MDD_IDEALIZED_PCT == -15.7
    assert STRATEGY_MDD_STRESS_PCT == -20.0


def test_default_config_matches_user_choices():
    c = RiskConfig()
    assert _approx(c.per_trade_fraction, 0.10)  # f = 10%
    assert c.max_concurrent == 3  # K = 3
    assert _approx(c.daily_loss_limit_pct, 3.0)  # daily -3%
    assert c.consecutive_loss_tiers == DEFAULT_CONSECUTIVE_LOSS_TIERS


def test_config_is_immutable():
    c = RiskConfig()
    with pytest.raises(FrozenInstanceError):
        c.per_trade_fraction = 0.2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Config validation.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"per_trade_fraction": 0.0},
        {"per_trade_fraction": 1.5},
        {"max_concurrent": 0},
        {"daily_loss_limit_pct": 0.0},
        {"tp_pct": 0.0},
        {"sl_pct": 0.0},
        {"cost_bps": -1.0},
        {"max_participation": 0.0},
        {"monthly_derisk_scale": 1.5},
        {"consecutive_loss_tiers": ((5, 0.5), (3, 0.25))},  # not ascending
        {"consecutive_loss_tiers": ((3, 1.5),)},  # scale > 1
        {"consecutive_loss_tiers": ((0, 0.5),)},  # min_streak < 1
    ],
)
def test_config_rejects_bad_params(kwargs):
    with pytest.raises(ValueError):
        RiskConfig(**kwargs)


# ---------------------------------------------------------------------------
# Per-trade notional + liquidity cap.
# ---------------------------------------------------------------------------
def test_position_notional_base_fraction():
    c = RiskConfig()
    assert _approx(position_notional_won(ONE_EOK, c), 10_000_000, tol=1e-3)
    assert _approx(position_notional_won(ONE_CHEON, c), 1_000_000, tol=1e-3)


def test_position_notional_fraction_override():
    c = RiskConfig()
    # A de-risked fraction (e.g. 0.05) shrinks the order.
    assert _approx(
        position_notional_won(ONE_EOK, c, fraction=0.05), 5_000_000, tol=1e-3
    )


def test_position_notional_liquidity_cap_binds_for_thin_name():
    c = RiskConfig()  # max_participation = 1.0
    # Base would be 10,000,000 but the entry second only traded 5,000,000 ->
    # the order is capped at one second of traded value.
    capped = position_notional_won(
        ONE_EOK, c, entry_liquidity_won=5_000_000
    )
    assert _approx(capped, 5_000_000, tol=1e-3)
    # A liquid name (50,000,000/s) does NOT bind -> full base size.
    liquid = position_notional_won(
        ONE_EOK, c, entry_liquidity_won=50_000_000
    )
    assert _approx(liquid, 10_000_000, tol=1e-3)


def test_position_notional_zero_fraction_floors_at_zero():
    # A halted entry (effective fraction 0.0) sizes to zero notional.
    c = RiskConfig()
    assert _approx(position_notional_won(ONE_EOK, c, fraction=0.0), 0.0, tol=1e-9)


def test_position_notional_rejects_bad_inputs():
    c = RiskConfig()
    with pytest.raises(ValueError):
        position_notional_won(-1, c)
    with pytest.raises(ValueError):
        position_notional_won(ONE_EOK, c, fraction=1.5)
    with pytest.raises(ValueError):
        position_notional_won(ONE_EOK, c, entry_liquidity_won=-1)


# ---------------------------------------------------------------------------
# 1R (per-trade risk).
# ---------------------------------------------------------------------------
def test_risk_per_trade_won_is_sl_plus_cost():
    c = RiskConfig()
    # 1억 -> notional 1,000만 -> R = 1,000만 * (1% + 0.23%) = 123,000.
    assert _approx(risk_per_trade_won(10_000_000, c), 123_000, tol=1e-3)


def test_risk_unit_account_pct_is_0_123():
    c = RiskConfig()
    assert _approx(risk_unit_account_pct(c), 0.123)


def test_risk_per_trade_rejects_negative():
    with pytest.raises(ValueError):
        risk_per_trade_won(-1, RiskConfig())


# ---------------------------------------------------------------------------
# Daily loss limit & halt.
# ---------------------------------------------------------------------------
def test_daily_loss_limit_won():
    c = RiskConfig()
    assert _approx(daily_loss_limit_won(ONE_EOK, c), 3_000_000, tol=1e-3)
    assert _approx(daily_loss_limit_won(ONE_CHEON, c), 300_000, tol=1e-3)


def test_should_halt_day_at_or_below_negative_limit():
    c = RiskConfig()  # 1억 -> limit 3,000,000
    assert should_halt_day(-3_000_000, ONE_EOK, c) is True  # exactly at limit
    assert should_halt_day(-3_500_000, ONE_EOK, c) is True  # past limit
    assert should_halt_day(-2_999_999, ONE_EOK, c) is False  # not yet
    assert should_halt_day(+100_000, ONE_EOK, c) is False  # a winning day
    # Scales with account size: 1천만 -> limit 300,000.
    assert should_halt_day(-300_000, ONE_CHEON, c) is True
    assert should_halt_day(-299_999, ONE_CHEON, c) is False


def test_should_halt_day_zero_account_halts_conservatively():
    # A zero-balance account has a zero limit, so break-even (or any loss) halts
    # it — the conservative contract (no capital -> no new entries).
    c = RiskConfig()
    assert should_halt_day(0.0, 0, c) is True


def test_daily_limit_in_r_is_about_24():
    c = RiskConfig()
    # 3% / 0.123% ~= 24.39R -> loose backstop, not the primary control.
    assert _approx(daily_limit_in_r(c), 24.390243, tol=1e-3)


# ---------------------------------------------------------------------------
# Concurrency exposure.
# ---------------------------------------------------------------------------
def test_max_concurrent_exposure():
    c = RiskConfig()
    assert _approx(max_concurrent_exposure_pct(c), 30.0)  # f*K = 10%*3
    assert _approx(
        max_concurrent_exposure_won(ONE_EOK, c), 30_000_000, tol=1e-3
    )


def test_worst_case_concurrent_loss():
    c = RiskConfig()
    # K * R at base notional: 3 * 123,000 = 369,000 (= 0.369% of 1억).
    assert _approx(
        worst_case_concurrent_loss_won(ONE_EOK, c), 369_000, tol=1e-3
    )


def test_worst_case_concurrent_loss_respects_liquidity_cap():
    c = RiskConfig()  # max_participation = 1.0
    # A thin name caps each entry at 5,000,000 (vs 10,000,000 base) -> per-
    # position R = 5,000,000 * 0.0123 = 61,500; K=3 -> 184,500.
    loss = worst_case_concurrent_loss_won(
        ONE_EOK, c, entry_liquidity_won=5_000_000
    )
    assert _approx(loss, 184_500, tol=1e-3)


# ---------------------------------------------------------------------------
# Consecutive-loss de-risking (calibrated to max streak 9).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "streak,expected",
    [
        (0, 1.0),
        (2, 1.0),
        (3, 0.5),
        (4, 0.5),
        (5, 0.25),
        (6, 0.25),
        (7, 0.0),
        (9, 0.0),
    ],
)
def test_consecutive_loss_scale_tiers(streak, expected):
    assert _approx(consecutive_loss_scale(streak), expected)


def test_consecutive_loss_scale_rejects_negative_streak():
    with pytest.raises(ValueError):
        consecutive_loss_scale(-1)


def test_consecutive_loss_scale_custom_tiers_last_match_wins():
    # Non-monotonic scales: the LAST tier whose min_streak <= streak applies,
    # so the break-based selection must pick 0.8 (tier @4), not 0.3 (tier @2).
    tiers = ((2, 0.3), (4, 0.8))
    assert _approx(consecutive_loss_scale(1, tiers), 1.0)  # below first tier
    assert _approx(consecutive_loss_scale(3, tiers), 0.3)  # only @2 matches
    assert _approx(consecutive_loss_scale(5, tiers), 0.8)  # last match wins


# ---------------------------------------------------------------------------
# effective_fraction: consecutive-loss + monthly de-risk combined.
# ---------------------------------------------------------------------------
def test_effective_fraction_base_is_full_f():
    c = RiskConfig()
    assert _approx(effective_fraction(c, consecutive_losses=0), 0.10)


def test_effective_fraction_applies_consecutive_scale():
    c = RiskConfig()
    assert _approx(effective_fraction(c, consecutive_losses=3), 0.05)
    assert _approx(effective_fraction(c, consecutive_losses=5), 0.025)
    assert _approx(effective_fraction(c, consecutive_losses=7), 0.0)


def test_effective_fraction_monthly_derisk():
    c = RiskConfig()
    # A losing month (<= -1.5%) halves the fraction; a mild month does not.
    assert _approx(
        effective_fraction(c, consecutive_losses=0, month_return_pct=-2.0), 0.05
    )
    assert _approx(
        effective_fraction(c, consecutive_losses=0, month_return_pct=-1.0), 0.10
    )
    # Both de-risks compound: 3-loss streak (0.5) in a losing month (0.5).
    assert _approx(
        effective_fraction(c, consecutive_losses=3, month_return_pct=-2.0),
        0.025,
    )


def test_effective_fraction_never_exceeds_base_and_floors_at_zero():
    c = RiskConfig()
    for streak in range(0, 12):
        f = effective_fraction(c, consecutive_losses=streak, month_return_pct=-9.0)
        assert 0.0 <= f <= c.per_trade_fraction


# ---------------------------------------------------------------------------
# Drawdown translation & expectancy.
# ---------------------------------------------------------------------------
def test_account_mdd_sequential_and_concurrent():
    # Sequential (factor 1.0): strategy MDD * f.
    assert _approx(account_mdd_estimate_pct(-15.7, 0.10), -1.57)
    assert _approx(account_mdd_estimate_pct(-20.0, 0.10), -2.0)
    # Worst-case concurrency up to K=3 deepens it.
    assert _approx(
        account_mdd_estimate_pct(-15.7, 0.10, concurrency_factor=3.0), -4.71
    )


def test_account_mdd_rejects_bad_inputs():
    with pytest.raises(ValueError):
        account_mdd_estimate_pct(-15.7, 1.5)  # fraction out of range
    with pytest.raises(ValueError):
        account_mdd_estimate_pct(-15.7, 0.10, concurrency_factor=0.0)


def test_expected_pnl_won():
    # 1억 -> notional 1,000만; idealized +0.952% -> +95,200; stress +0.811% -> +81,100.
    assert _approx(expected_pnl_won(10_000_000, 0.952), 95_200, tol=1e-3)
    assert _approx(expected_pnl_won(10_000_000, 0.811), 81_100, tol=1e-3)


def test_expected_pnl_rejects_negative_notional():
    with pytest.raises(ValueError):
        expected_pnl_won(-1, 0.952)


# ---------------------------------------------------------------------------
# Kelly is degenerate for a tight-SL strategy (justifies drawdown-based sizing).
# ---------------------------------------------------------------------------
def test_full_kelly_is_degenerate_for_tight_sl():
    # p=0.42, win=+4.77% (TP-cost), loss=1.23% (SL+cost) -> f* ~= 21.99 (2,199%).
    kelly = full_kelly_fraction(0.42, 4.77, 1.23)
    assert _approx(kelly, 21.987, tol=1e-2)
    # Chosen f=10% is far below full Kelly (ultra-conservative).
    assert 0.10 < kelly


def test_full_kelly_rejects_bad_inputs():
    with pytest.raises(ValueError):
        full_kelly_fraction(1.5, 4.77, 1.23)  # win_rate out of range
    with pytest.raises(ValueError):
        full_kelly_fraction(0.42, 0.0, 1.23)  # non-positive win return
    with pytest.raises(ValueError):
        full_kelly_fraction(0.42, 4.77, 0.0)  # non-positive loss return


# ---------------------------------------------------------------------------
# plan_for_account: the doc's worked-example table (1천만 / 5천만 / 1억).
# ---------------------------------------------------------------------------
def test_plan_for_account_one_eok_matches_doc():
    c = RiskConfig()
    p = plan_for_account(c, ONE_EOK)
    assert _approx(p["notional_won"], 10_000_000, tol=1e-3)
    assert _approx(p["risk_per_trade_won"], 123_000, tol=1e-3)
    assert _approx(p["risk_unit_account_pct"], 0.123)
    assert _approx(p["daily_loss_limit_won"], 3_000_000, tol=1e-3)
    assert _approx(p["daily_limit_in_r"], 24.390243, tol=1e-3)
    assert _approx(p["max_concurrent_exposure_won"], 30_000_000, tol=1e-3)
    assert _approx(p["max_concurrent_exposure_pct"], 30.0)
    assert _approx(p["worst_case_concurrent_loss_won"], 369_000, tol=1e-3)
    assert _approx(p["expected_pnl_idealized_won"], 95_200, tol=1e-3)
    assert _approx(p["expected_pnl_stress_won"], 81_100, tol=1e-3)
    assert _approx(p["account_mdd_idealized_pct"], -1.57)
    assert _approx(p["account_mdd_stress_pct"], -2.0)


def test_plan_for_account_one_cheon_matches_doc():
    c = RiskConfig()
    p = plan_for_account(c, ONE_CHEON)
    assert _approx(p["notional_won"], 1_000_000, tol=1e-3)
    assert _approx(p["risk_per_trade_won"], 12_300, tol=1e-3)
    assert _approx(p["daily_loss_limit_won"], 300_000, tol=1e-3)
    assert _approx(p["max_concurrent_exposure_won"], 3_000_000, tol=1e-3)
    assert _approx(p["worst_case_concurrent_loss_won"], 36_900, tol=1e-3)
    assert _approx(p["expected_pnl_idealized_won"], 9_520, tol=1e-3)
    assert _approx(p["expected_pnl_stress_won"], 8_110, tol=1e-3)


def test_plan_for_account_five_cheon_matches_doc():
    c = RiskConfig()
    p = plan_for_account(c, FIVE_CHEON)
    assert _approx(p["notional_won"], 5_000_000, tol=1e-3)
    assert _approx(p["risk_per_trade_won"], 61_500, tol=1e-3)
    assert _approx(p["daily_loss_limit_won"], 1_500_000, tol=1e-3)
    assert _approx(p["max_concurrent_exposure_won"], 15_000_000, tol=1e-3)
    assert _approx(p["worst_case_concurrent_loss_won"], 184_500, tol=1e-3)
    assert _approx(p["expected_pnl_idealized_won"], 47_600, tol=1e-3)
    assert _approx(p["expected_pnl_stress_won"], 40_550, tol=1e-3)


def test_plan_scales_linearly_with_account():
    c = RiskConfig()
    p1 = plan_for_account(c, ONE_CHEON)
    p10 = plan_for_account(c, ONE_EOK)
    # 1억 is 10x 1천만 -> all 원 quantities scale 10x; ratios are invariant.
    assert _approx(p10["notional_won"], p1["notional_won"] * 10, tol=1e-3)
    assert _approx(p10["risk_per_trade_won"], p1["risk_per_trade_won"] * 10, tol=1e-3)
    assert _approx(p10["risk_unit_account_pct"], p1["risk_unit_account_pct"])
    assert _approx(p10["daily_limit_in_r"], p1["daily_limit_in_r"])
