"""Position sizing & risk control for the 시초 갭상승 (opening gap-up) strategy.

**RULE strategy, NOT reinforcement learning.**  Every number this module
produces describes the user's pre-registered gap-up *rule* (등락율>=2% entry +
``ts_imb`` demand filter + TP5/SL1 + 09:25 time-exit), never an RL/PPO/DQN
policy.  See ``docs/stom_rl_gap_up_risk_sizing_2026-05-29.md`` (Page A) and the
resume anchor ``docs/stom_rl_resume_commit_2026-05-29.md``.

Design (locked, 2026-05-29)
---------------------------
The verified edge (bounded universe, N=235, ``ts_imb`` filter, 23 bp real cost)
is::

    expectancy/trade  +0.952% idealized / +0.811% sl_gap_stress
    win rate          ~42%
    max loss streak   9
    strategy MDD      -15.7% idealized / ~-20% stress  (full-notional curve)

Sizing is governed by **drawdown tolerance and concurrency, NOT Kelly** — the
tight -1% SL caps a single loss at ~1.23% of notional, which makes full Kelly
degenerate (~22x account; see :func:`full_kelly_fraction`).  The user-chosen
policy is ``f=10%`` per entry, ``K=3`` concurrent, daily ``-3%`` halt.

All functions here are PURE (no I/O, no DB, no clock); they are unit-tested on
known values in ``tests/test_stom_rl_gap_up_risk_sizing.py``.  Monetary inputs
are Korean won (``_won`` suffix); ratios are percent (``_pct``) or R-multiples
(``_r``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Verified strategy constants (ts_imb filter, 23 bp real round-trip cost).
# These mirror the locked numbers in the Page A doc; they are descriptive
# defaults, not tuned parameters.
# ---------------------------------------------------------------------------
PRIMARY_FILTER: str = "ts_imb"  # 체결강도>=100 AND 호가 imbalance>=0.5
DEFAULT_TP_PCT: float = 5.0
DEFAULT_SL_PCT: float = 1.0
DEFAULT_COST_BPS: float = 23.0  # 0.015%x2 commission + 0.20% sell tax = 23 bp
IDEALIZED_EXPECTANCY_PCT: float = 0.952  # net %/trade @23bp, idealized fills
STRESS_EXPECTANCY_PCT: float = 0.811  # net %/trade @23bp, sl_gap_stress fills
WIN_RATE: float = 0.42
MAX_LOSS_STREAK: int = 9
STRATEGY_MDD_IDEALIZED_PCT: float = -15.7  # full-notional per-trade-% curve
STRATEGY_MDD_STRESS_PCT: float = -20.0

# Consecutive-loss de-risking tiers as ``(min_streak, fraction_scale)`` sorted
# ascending by streak.  The LAST tier whose ``min_streak <= current streak``
# applies; below the first tier the scale is 1.0 (full size).  A 0.0 scale means
# "halt new entries".  Calibrated to the observed max loss streak of 9: size is
# cut at 3 and 5, and entries halt at 7 — before the historical worst is reached.
DEFAULT_CONSECUTIVE_LOSS_TIERS: Tuple[Tuple[int, float], ...] = (
    (3, 0.5),
    (5, 0.25),
    (7, 0.0),
)


# ---------------------------------------------------------------------------
# Risk policy (immutable).  Dynamic state (account, streak, month P&L) is passed
# to the functions as arguments — the config holds only the fixed policy.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskConfig:
    """Immutable risk-sizing policy for the gap-up RULE strategy.

    ``per_trade_fraction`` (f) is the notional fraction of the account deployed
    on ONE entry; ``max_concurrent`` (K) caps simultaneous positions, so the
    peak deployed capital is ``f*K`` of the account.  ``daily_loss_limit_pct``
    halts new entries once the day's realized loss reaches that percent of the
    account.  ``max_participation`` caps a single order at that multiple of the
    entry bar's 초당거래대금 (per-second traded value) — a coarse Page-A liquidity
    guard refined in Page C.  ``monthly_derisk_*`` cut size in a losing month
    (the 2022-style soft-regime absorber).
    """

    per_trade_fraction: float = 0.10  # f
    max_concurrent: int = 3  # K
    daily_loss_limit_pct: float = 3.0  # halt the day at -3% of account
    tp_pct: float = DEFAULT_TP_PCT
    sl_pct: float = DEFAULT_SL_PCT
    cost_bps: float = DEFAULT_COST_BPS
    max_participation: float = 1.0  # notional cap = this x entry 초당거래대금
    idealized_expectancy_pct: float = IDEALIZED_EXPECTANCY_PCT
    stress_expectancy_pct: float = STRESS_EXPECTANCY_PCT
    monthly_derisk_threshold_pct: float = -1.5  # month <= -1.5% -> de-risk
    monthly_derisk_scale: float = 0.5
    consecutive_loss_tiers: Tuple[Tuple[int, float], ...] = (
        DEFAULT_CONSECUTIVE_LOSS_TIERS  # immutable tuple -> safe as a default
    )

    def __post_init__(self) -> None:
        if not (0.0 < self.per_trade_fraction <= 1.0):
            raise ValueError("per_trade_fraction must be in (0, 1]")
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if self.daily_loss_limit_pct <= 0.0:
            raise ValueError("daily_loss_limit_pct must be > 0")
        if self.tp_pct <= 0.0 or self.sl_pct <= 0.0:
            raise ValueError("tp_pct and sl_pct must be > 0")
        if self.cost_bps < 0.0:
            raise ValueError("cost_bps must be >= 0")
        if self.max_participation <= 0.0:
            raise ValueError("max_participation must be > 0")
        if not (0.0 <= self.monthly_derisk_scale <= 1.0):
            raise ValueError("monthly_derisk_scale must be in [0, 1]")
        _validate_tiers(self.consecutive_loss_tiers)


def _validate_tiers(tiers: Tuple[Tuple[int, float], ...]) -> None:
    """Validate de-risk tiers: ascending streaks, scales in [0, 1]."""

    prev_streak: Optional[int] = None
    for entry in tiers:
        if len(entry) != 2:
            raise ValueError("each tier must be (min_streak, scale)")
        streak, scale = entry
        if int(streak) < 1:
            raise ValueError("tier min_streak must be >= 1")
        if not (0.0 <= float(scale) <= 1.0):
            raise ValueError("tier scale must be in [0, 1]")
        if prev_streak is not None and int(streak) <= prev_streak:
            raise ValueError("tiers must be sorted by ascending min_streak")
        prev_streak = int(streak)


# ---------------------------------------------------------------------------
# Per-trade sizing.
# ---------------------------------------------------------------------------
def position_notional_won(
    account_won: float,
    config: RiskConfig,
    *,
    fraction: Optional[float] = None,
    entry_liquidity_won: Optional[float] = None,
) -> float:
    """Notional (원) to deploy on one entry.

    Uses ``fraction`` when supplied (e.g. the de-risked :func:`effective_fraction`)
    otherwise ``config.per_trade_fraction``.  When ``entry_liquidity_won`` (the
    entry bar's 초당거래대금) is supplied, the order is capped at
    ``config.max_participation * entry_liquidity_won`` so a thin name auto-shrinks
    the order (the Page-A liquidity guard).
    """

    if account_won < 0:
        raise ValueError("account_won must be >= 0")
    f = config.per_trade_fraction if fraction is None else float(fraction)
    if not (0.0 <= f <= 1.0):
        raise ValueError("fraction must be in [0, 1]")
    base = f * float(account_won)
    if entry_liquidity_won is not None:
        if entry_liquidity_won < 0:
            raise ValueError("entry_liquidity_won must be >= 0")
        cap = config.max_participation * float(entry_liquidity_won)
        return min(base, cap)
    return base


def risk_per_trade_won(notional_won: float, config: RiskConfig) -> float:
    """1R in 원 — the nominal stop-loss loss on a single position.

    A stop-out books ``SL% + round-trip cost`` against the notional::

        R = notional * (sl_pct/100 + cost_bps/10000)

    At SL=1% and cost=23 bp this is ``notional * 0.0123``.  This is the NOMINAL
    stop loss; a gap-through (sl_gap_stress) can exceed it — that tail is modelled
    in Page C, not here.
    """

    if notional_won < 0:
        raise ValueError("notional_won must be >= 0")
    loss_fraction = config.sl_pct / 100.0 + config.cost_bps / 10000.0
    return float(notional_won) * loss_fraction


def risk_unit_account_pct(config: RiskConfig) -> float:
    """1R as a percent of the account = ``f * (sl_pct + cost_bps/100)``.

    For f=10%, SL=1%, cost=23 bp this is ``0.123%`` of the account.
    """

    loss_fraction = config.sl_pct / 100.0 + config.cost_bps / 10000.0
    return config.per_trade_fraction * loss_fraction * 100.0


# ---------------------------------------------------------------------------
# Daily loss limit.
# ---------------------------------------------------------------------------
def daily_loss_limit_won(account_won: float, config: RiskConfig) -> float:
    """Daily loss limit in 원 (a POSITIVE magnitude) = ``account * limit%``."""

    if account_won < 0:
        raise ValueError("account_won must be >= 0")
    return float(account_won) * config.daily_loss_limit_pct / 100.0


def should_halt_day(
    realized_pnl_today_won: float,
    account_won: float,
    config: RiskConfig,
) -> bool:
    """True when today's realized P&L has reached the daily loss limit.

    ``realized_pnl_today_won`` is signed (NEGATIVE for a losing day).  The day
    halts when the loss magnitude meets or exceeds :func:`daily_loss_limit_won`,
    i.e. ``realized_pnl_today_won <= -limit``.
    """

    limit = daily_loss_limit_won(account_won, config)
    return float(realized_pnl_today_won) <= -limit


def daily_limit_in_r(config: RiskConfig) -> float:
    """Daily loss limit expressed in R multiples = ``limit% / R%``.

    For the default policy this is ``3% / 0.123% ~= 24.4R`` — loose given K=3 and
    intraday resolution, so the daily halt is a catastrophe backstop, not the
    primary control.
    """

    r_pct = risk_unit_account_pct(config)
    if r_pct <= 0.0:
        raise ValueError("risk unit percent must be > 0")
    return config.daily_loss_limit_pct / r_pct


# ---------------------------------------------------------------------------
# Concurrency exposure.
# ---------------------------------------------------------------------------
def max_concurrent_exposure_won(account_won: float, config: RiskConfig) -> float:
    """Peak simultaneous deployed capital = ``f * K * account``."""

    if account_won < 0:
        raise ValueError("account_won must be >= 0")
    return config.per_trade_fraction * config.max_concurrent * float(account_won)


def max_concurrent_exposure_pct(config: RiskConfig) -> float:
    """Peak simultaneous exposure as a percent of the account = ``f * K * 100``."""

    return config.per_trade_fraction * config.max_concurrent * 100.0


def worst_case_concurrent_loss_won(
    account_won: float,
    config: RiskConfig,
    *,
    entry_liquidity_won: Optional[float] = None,
) -> float:
    """Loss (POSITIVE magnitude) if all K concurrent positions hit the SL.

    ``K * R`` at the base per-trade notional.  At f=10%, K=3 this is
    ``3 * 0.123% = 0.369%`` of the account.  NOTE: this is the NOMINAL stop
    (SL level + cost); a gap-through (sl_gap_stress) can book a worse fill and
    exceed it — that tail is modelled in Page C, not here, so this is a
    lower bound on the true worst case, not an absolute ceiling.
    """

    notional = position_notional_won(
        account_won, config, entry_liquidity_won=entry_liquidity_won
    )
    return config.max_concurrent * risk_per_trade_won(notional, config)


# ---------------------------------------------------------------------------
# De-risking: consecutive-loss tiers + monthly soft-regime absorber.
# ---------------------------------------------------------------------------
def consecutive_loss_scale(
    streak: int,
    tiers: Tuple[Tuple[int, float], ...] = DEFAULT_CONSECUTIVE_LOSS_TIERS,
) -> float:
    """Fraction multiplier for the CURRENT consecutive-loss ``streak``.

    Returns 1.0 below the first tier; otherwise the scale of the highest tier
    whose ``min_streak <= streak``.  A 0.0 result means "halt new entries".  The
    streak is the number of consecutive losses SO FAR (reset to 0 by any win).
    """

    if streak < 0:
        raise ValueError("streak must be >= 0")
    _validate_tiers(tiers)
    scale = 1.0
    for min_streak, tier_scale in tiers:
        if streak >= min_streak:
            scale = float(tier_scale)
        else:
            break
    return scale


def effective_fraction(
    config: RiskConfig,
    consecutive_losses: int = 0,
    month_return_pct: Optional[float] = None,
) -> float:
    """Effective per-trade fraction after de-risking.

    Combines the base ``f`` with the consecutive-loss scale and, when
    ``month_return_pct`` (the running month's account return %) is at or below
    ``config.monthly_derisk_threshold_pct``, the monthly de-risk scale.  Returns
    a fraction in ``[0, f]`` (0.0 = no entry).
    """

    scale = consecutive_loss_scale(
        consecutive_losses, config.consecutive_loss_tiers
    )
    f = config.per_trade_fraction * scale
    if (
        month_return_pct is not None
        and float(month_return_pct) <= config.monthly_derisk_threshold_pct
    ):
        f *= config.monthly_derisk_scale
    return f


# ---------------------------------------------------------------------------
# Drawdown translation & expectancy.
# ---------------------------------------------------------------------------
def account_mdd_estimate_pct(
    strategy_mdd_pct: float,
    fraction: float,
    concurrency_factor: float = 1.0,
) -> float:
    """Translate the full-notional strategy MDD to an account-level MDD %.

    ``account_MDD ~= strategy_MDD * f * concurrency_factor``.  The strategy curve
    assumes sequential fixed-notional trades, so ``concurrency_factor=1.0`` is the
    sequential estimate (exact for that curve); values up to K are a heuristic
    stress factor for clustered concurrent losses (the path steepens) — an
    approximation, not a proven bound.  Inputs and the result are signed
    (negative for a drawdown); passing a positive ``strategy_mdd_pct`` is a
    caller error (it would yield a nonsensical positive "drawdown").
    """

    if not (0.0 <= fraction <= 1.0):
        raise ValueError("fraction must be in [0, 1]")
    if concurrency_factor <= 0.0:
        raise ValueError("concurrency_factor must be > 0")
    return float(strategy_mdd_pct) * fraction * concurrency_factor


def expected_pnl_won(notional_won: float, expectancy_pct: float) -> float:
    """Expected per-trade P&L in 원 = ``notional * expectancy% / 100``."""

    if notional_won < 0:
        raise ValueError("notional_won must be >= 0")
    return float(notional_won) * float(expectancy_pct) / 100.0


def full_kelly_fraction(
    win_rate: float,
    win_return_pct: float,
    loss_return_pct: float,
) -> float:
    """Growth-optimal notional fraction for the binary win/loss outcome.

    For a bet that returns ``+a`` (prob p) or ``-b`` (prob 1-p) per unit notional,
    the Kelly notional fraction is ``f* = (p*a - q*b) / (a*b)`` with
    ``a = win_return_pct/100`` and ``b = loss_return_pct/100`` (both POSITIVE
    magnitudes).  For this strategy (p=0.42, a=4.77%, b=1.23%) it is ~21.99 — a
    degenerate 2,199% of account, which is why sizing here is governed by
    drawdown/concurrency, not Kelly.  Chosen f=10% is ~1/220 of full Kelly.

    A NEGATIVE result signals a non-positive edge (``p*a <= q*b``) — do NOT size
    from it; it means "do not bet".
    """

    if not (0.0 <= win_rate <= 1.0):
        raise ValueError("win_rate must be in [0, 1]")
    a = float(win_return_pct) / 100.0
    b = float(loss_return_pct) / 100.0
    if a <= 0.0 or b <= 0.0:
        raise ValueError("win_return_pct and loss_return_pct must be > 0")
    q = 1.0 - float(win_rate)
    return (float(win_rate) * a - q * b) / (a * b)


# ---------------------------------------------------------------------------
# Account-level plan bundle (drives the doc's worked-example table).
# ---------------------------------------------------------------------------
def plan_for_account(config: RiskConfig, account_won: float) -> Dict[str, Any]:
    """Bundle every derived sizing/risk number for one account size.

    Returns base-size (no de-risk) values: the per-entry notional, 1R, the daily
    loss limit, peak concurrent exposure, the worst-case all-K stop-out, expected
    P&L per trade (idealized + stress) and the sequential account MDD estimates.
    Mirrors §3 of the Page A doc and is asserted in the tests.
    """

    if account_won < 0:
        raise ValueError("account_won must be >= 0")
    notional = position_notional_won(account_won, config)
    return {
        "account_won": float(account_won),
        "per_trade_fraction": config.per_trade_fraction,
        "notional_won": notional,
        "risk_per_trade_won": risk_per_trade_won(notional, config),
        "risk_unit_account_pct": risk_unit_account_pct(config),
        "daily_loss_limit_won": daily_loss_limit_won(account_won, config),
        "daily_limit_in_r": daily_limit_in_r(config),
        "max_concurrent_exposure_won": max_concurrent_exposure_won(
            account_won, config
        ),
        "max_concurrent_exposure_pct": max_concurrent_exposure_pct(config),
        "worst_case_concurrent_loss_won": worst_case_concurrent_loss_won(
            account_won, config
        ),
        "expected_pnl_idealized_won": expected_pnl_won(
            notional, config.idealized_expectancy_pct
        ),
        "expected_pnl_stress_won": expected_pnl_won(
            notional, config.stress_expectancy_pct
        ),
        "account_mdd_idealized_pct": account_mdd_estimate_pct(
            STRATEGY_MDD_IDEALIZED_PCT, config.per_trade_fraction
        ),
        "account_mdd_stress_pct": account_mdd_estimate_pct(
            STRATEGY_MDD_STRESS_PCT, config.per_trade_fraction
        ),
    }
