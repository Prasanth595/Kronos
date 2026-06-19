"""Causal microstructure features for the within-window predictability probe (Page R-P1).

**RULE strategy, NOT reinforcement learning.**  This module only builds CAUSAL
(point-in-time, no look-ahead) feature vectors from the per-second orderbook +
order-flow sequence UP TO a decision second ``t``.  It does not trade or learn;
it feeds the supervised predictability gate (see ``predictability_probe.py``)
that decides — cheaply, before any deep RL — whether the intra-window sequence
carries cost-relevant short-horizon signal at all.

All functions are PURE (no I/O).  Causality is structural: callers pass ONLY the
rows at or before ``t`` (``window`` = ``rows[0..t]``); nothing here can see the
future because the future rows are never given to it.
"""

from __future__ import annotations

from math import isfinite
from statistics import pstdev
from typing import Any, Dict, List, Optional, Sequence

# Trailing look-back lengths (in bars ~ seconds) for rolling features.
LOOKBACKS: tuple = (5, 15, 30, 60)


def pct_return(p_from: float, p_to: float) -> Optional[float]:
    """Percent return ``(p_to/p_from - 1)*100``; None if ``p_from`` non-positive."""

    if p_from is None or p_to is None or p_from <= 0:
        return None
    return (float(p_to) / float(p_from) - 1.0) * 100.0


def imbalance(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """``a / (a + b)`` in [0, 1]; None if either side missing or sum non-positive."""

    if a is None or b is None:
        return None
    s = float(a) + float(b)
    if s <= 0:
        return None
    return float(a) / s


def signed_flow(buy: Optional[float], sell: Optional[float]) -> float:
    """Signed flow ``buy - sell`` (0.0 for missing components)."""

    return float(buy or 0.0) - float(sell or 0.0)


def linfit_slope(ys: Sequence[float]) -> float:
    """Least-squares slope of ``ys`` vs index 0..n-1 (0.0 for < 2 points)."""

    vals = [float(v) for v in ys if v is not None and isfinite(float(v))]
    n = len(vals)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(vals) / n
    num = sum((i - mean_x) * (vals[i] - mean_y) for i in range(n))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def microprice(
    bid: Optional[float], ask: Optional[float],
    bid_qty: Optional[float], ask_qty: Optional[float],
) -> Optional[float]:
    """Depth-weighted microprice ``(bid*ask_qty + ask*bid_qty)/(bid_qty+ask_qty)``.

    Heavier resting size on one side pulls the microprice toward the OTHER side's
    quote (the side likely to be hit).  None if quotes/sizes missing or empty.
    """

    if None in (bid, ask, bid_qty, ask_qty):
        return None
    q = float(bid_qty) + float(ask_qty)
    if q <= 0:
        return None
    return (float(bid) * float(ask_qty) + float(ask) * float(bid_qty)) / q


def depth_ofi(
    prev_bid_tot: Optional[float], prev_ask_tot: Optional[float],
    bid_tot: Optional[float], ask_tot: Optional[float],
) -> float:
    """Approximate order-flow imbalance from consecutive 1s depth deltas.

    ``Δbid_total - Δask_total`` between two snapshots.  This is an APPROXIMATION of
    true (message-level) OFI inferred from 1s aggregated depth, so it is noisier
    than book-event OFI — labelled as such in the probe.
    """

    d_bid = float(bid_tot or 0.0) - float(prev_bid_tot or 0.0)
    d_ask = float(ask_tot or 0.0) - float(prev_ask_tot or 0.0)
    return d_bid - d_ask


def _last_k(seq: Sequence[Any], k: int) -> List[Any]:
    return list(seq[-k:]) if k > 0 else []


def causal_feature_vector(window: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Build the causal feature vector at the LAST row of ``window`` (= decision t).

    ``window`` is the list of per-second rows ``rows[0..t]`` (causal — never pass
    future rows).  Each row dict carries: ``sec`` (seconds since 09:00), ``price``,
    ``buy_val``/``sell_val`` (per-sec buy/sell value), ``buy_qty``/``sell_qty``,
    ``ts`` (체결강도), ``bid_tot``/``ask_tot`` (총잔량), ``bid1``/``ask1`` (best
    quotes), ``bidq1``/``askq1`` (best-level depth).  Returns an ordered dict of
    float features; missing inputs collapse to 0.0 so the vector is always dense.
    """

    if not window:
        raise ValueError("window must contain at least the decision row")
    n = len(window)
    cur = window[-1]
    prices = [r.get("price") for r in window]
    p_t = prices[-1]

    feats: Dict[str, float] = {}

    # --- time / price state ---
    sec = float(cur.get("sec") or 0.0)
    feats["t_sec"] = sec
    feats["t_frac"] = sec / 1200.0  # fraction through the 09:00-09:20 window
    feats["ret_open"] = pct_return(prices[0], p_t) or 0.0

    # --- trailing returns + realized vol per look-back ---
    for k in LOOKBACKS:
        idx = max(0, n - 1 - k)
        feats[f"ret_{k}"] = pct_return(prices[idx], p_t) or 0.0
        seg = prices[max(0, n - k):]
        rets = [
            pct_return(seg[i - 1], seg[i]) or 0.0 for i in range(1, len(seg))
        ]
        feats[f"vol_{k}"] = pstdev(rets) if len(rets) >= 2 else 0.0

    # --- signed order flow per look-back (value + ratio) ---
    for k in LOOKBACKS:
        rows_k = _last_k(window, k)
        sval = sum(signed_flow(r.get("buy_val"), r.get("sell_val")) for r in rows_k)
        buy = sum(float(r.get("buy_val") or 0.0) for r in rows_k)
        sell = sum(float(r.get("sell_val") or 0.0) for r in rows_k)
        feats[f"sflow_val_{k}"] = sval
        feats[f"sflow_ratio_{k}"] = imbalance(buy, sell) if (buy + sell) > 0 else 0.5

    # --- trade strength (체결강도) level + trailing slope ---
    feats["ts_level"] = float(cur.get("ts") or 0.0)
    feats["ts_slope_30"] = linfit_slope([r.get("ts") for r in _last_k(window, 30)])

    # --- book shape (5-level totals + best level) ---
    feats["book_imb_tot"] = imbalance(cur.get("bid_tot"), cur.get("ask_tot")) or 0.5
    feats["book_imb_l1"] = imbalance(cur.get("bidq1"), cur.get("askq1")) or 0.5

    # --- approximate depth OFI over look-backs ---
    for k in LOOKBACKS:
        rows_k = _last_k(window, k + 1)
        ofi = sum(
            depth_ofi(
                rows_k[i - 1].get("bid_tot"), rows_k[i - 1].get("ask_tot"),
                rows_k[i].get("bid_tot"), rows_k[i].get("ask_tot"),
            )
            for i in range(1, len(rows_k))
        )
        feats[f"ofi_{k}"] = ofi

    # --- microprice deviation + relative spread ---
    mp = microprice(cur.get("bid1"), cur.get("ask1"), cur.get("bidq1"), cur.get("askq1"))
    bid1, ask1 = cur.get("bid1"), cur.get("ask1")
    if mp is not None and bid1 and ask1:
        mid = (float(bid1) + float(ask1)) / 2.0
        feats["micro_dev"] = ((mp - mid) / mid * 100.0) if mid > 0 else 0.0
        feats["spread_rel"] = ((float(ask1) - float(bid1)) / mid * 100.0) if mid > 0 else 0.0
    else:
        feats["micro_dev"] = 0.0
        feats["spread_rel"] = 0.0

    return feats


FEATURE_NAMES: List[str] = list(
    causal_feature_vector(
        [{"sec": 0, "price": 100.0}, {"sec": 1, "price": 100.0}]
    ).keys()
)
