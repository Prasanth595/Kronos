"""De-idealized marketable fills + rule-from-arbitrary-entry simulator (Page P1b).

**RULE strategy, NOT reinforcement learning.**

The predictability gate (P1) measured a real ranking signal but scored it with
IDEALIZED fills (현재가 returns − flat 23bp) and NOT baseline-relative.  P1b fixes
both: trades fill MARKETABLE (a buy pays the ask 매도호가1, a sell hits the bid
매수호가1, so the spread is paid twice) plus optional extra slippage, and the rule
is simulated from an ARBITRARY entry bar so a model's chosen entry can be compared
paired against the rule's fixed 09:00 entry.

Pure functions (no I/O); unit-tested on synthetic paths.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

EXIT_TP = "tp"
EXIT_SL = "sl"
EXIT_TIME = "time"
DEFAULT_TIME_EXIT_SEC = 1500  # 09:25:00 = 25*60 seconds after 09:00


def marketable_entry_price(
    bid1: Optional[float], ask1: Optional[float], price: float, *, slippage_bps: float = 0.0
) -> float:
    """Marketable BUY fill: pay the ask (cross the spread), + slippage.

    Falls back to ``price`` when the ask is missing/non-positive.
    """

    if slippage_bps < 0:
        raise ValueError("slippage_bps must be >= 0")
    p = float(ask1) if (ask1 is not None and float(ask1) > 0) else float(price)
    return p * (1.0 + slippage_bps / 10000.0)


def marketable_exit_price(
    bid1: Optional[float], ask1: Optional[float], price: float, *, slippage_bps: float = 0.0
) -> float:
    """Marketable SELL fill: hit the bid (cross the spread), − slippage.

    Falls back to ``price`` when the bid is missing/non-positive.
    """

    if slippage_bps < 0:
        raise ValueError("slippage_bps must be >= 0")
    p = float(bid1) if (bid1 is not None and float(bid1) > 0) else float(price)
    return p * (1.0 - slippage_bps / 10000.0)


def simulate_rule_from_entry(
    prices: Sequence[float],
    bids: Sequence[Optional[float]],
    asks: Sequence[Optional[float]],
    secs: Sequence[int],
    entry_idx: int,
    *,
    tp_pct: float = 5.0,
    sl_pct: float = 1.0,
    time_exit_sec: int = DEFAULT_TIME_EXIT_SEC,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
) -> Tuple[float, str]:
    """Net % of the TP/SL/time rule entered MARKETABLE at ``entry_idx``.

    Buy fills at the ask at ``entry_idx``; the forward walk exits at the first bar
    that (a) reaches the time-exit second (09:25), else (b) trips SL (price <= SL
    level, checked before TP — conservative), else (c) trips TP.  The exit fills
    MARKETABLE at that bar's bid.  ``cost_bps`` (commission+tax) is subtracted on
    top of the spread already paid by the marketable fills.  Returns
    ``(net_return_pct, exit_reason)``.
    """

    n = len(prices)
    if not (0 <= entry_idx < n):
        raise ValueError("entry_idx out of range")
    if tp_pct <= 0 or sl_pct <= 0:
        raise ValueError("tp_pct and sl_pct must be > 0")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")

    entry_fill = marketable_entry_price(
        bids[entry_idx], asks[entry_idx], prices[entry_idx], slippage_bps=slippage_bps
    )
    if entry_fill <= 0:
        raise ValueError("entry fill must be positive")
    tp_level = entry_fill * (1.0 + tp_pct / 100.0)
    sl_level = entry_fill * (1.0 - sl_pct / 100.0)

    exit_idx = n - 1
    reason = EXIT_TIME
    for j in range(entry_idx + 1, n):
        if int(secs[j]) >= time_exit_sec:
            exit_idx, reason = j, EXIT_TIME
            break
        p = float(prices[j])
        if p <= sl_level:  # conservative: SL wins a same-bar straddle
            exit_idx, reason = j, EXIT_SL
            break
        if p >= tp_level:
            exit_idx, reason = j, EXIT_TP
            break

    exit_fill = marketable_exit_price(
        bids[exit_idx], asks[exit_idx], prices[exit_idx], slippage_bps=slippage_bps
    )
    net = (exit_fill / entry_fill - 1.0) * 100.0 - cost_bps / 100.0
    return net, reason
