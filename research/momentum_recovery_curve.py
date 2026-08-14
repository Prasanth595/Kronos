#!/usr/bin/env python3
"""Threshold-free drawdown/recovery analysis on the corrected Cameron entries.

Episodes are defined WITHOUT any minimum size: an episode begins the moment
price trades below the running high and ends when a new high is made
(recovered) or the session ends (terminal). Every retracement, however
small, is an event; depth grids below are REPORTING cuts, never event
definitions. Within a ticker-day, every interim episode recovers by
construction; at most one terminal episode per day fails.

Primary object: the recovery curve
    P(new high | retracement reached >= X%)   for a grid of X
with event-weighted and ticker-day-weighted versions, a ticker-day cluster
bootstrap 95% CI, conditional rebound/leg magnitudes, time-to-recovery from
the X-crossing, and conditional terminal loss when recovery never comes.

Bar-order convention: within a bar the low is applied before the high
(depth measured through the bar that recovers). Descriptive only.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_recovery_curve.py
"""
import json
import os
import random

from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = {"OOS": os.environ["MOMO_OOS"], "IS": os.environ["MOMO_IS"]}
GRID = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30]


def tmin(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def episodes_for(t):
    """Zero-threshold decomposition of one post-entry path."""
    path = t["path"]
    t0 = tmin(path[0]["t"])
    peak = path[0]["h"]
    peak_t = 0
    eps = []
    cur = None
    for b in path:
        mt = tmin(b["t"]) - t0
        # low first (convention)
        if b["l"] < peak and (cur is None or b["l"] < cur["trough"]):
            if cur is None:
                cur = {"peak": peak, "peak_t": peak_t, "trough": b["l"],
                       "trough_t": mt, "cross_t": {}}
            else:
                cur["trough"], cur["trough_t"] = b["l"], mt
            d = (cur["peak"] - cur["trough"]) / cur["peak"] * 100
            for X in GRID:
                if d >= X and X not in cur["cross_t"]:
                    cur["cross_t"][X] = mt
        if b["h"] > peak:
            if cur is not None:
                cur["recovered"] = True
                cur["rec_t"] = mt
                eps.append(cur)
                cur = None
            peak, peak_t = b["h"], mt
    if cur is not None:
        cur["recovered"] = False
        cur["close_px"] = path[-1]["c"]
        eps.append(cur)
    for ep in eps:
        ep["depth"] = (ep["peak"] - ep["trough"]) / ep["peak"] * 100
        ep["peak_pct"] = (ep["peak"] / t["entry_px_raw"] - 1) * 100
    return eps


def scale_next_leg(t, X):
    """At reporting scale X: after each recovered >=X% retracement, how much
    higher is the NEXT >=X% retracement's peak vs the recovered peak."""
    path = t["path"]
    peak = path[0]["h"]
    events = []           # (peak, recovered)
    cur_peak = peak
    in_pb = False
    trough = None
    out = []
    for b in path:
        if not in_pb:
            if b["h"] > cur_peak:
                cur_peak = b["h"]
            if b["l"] <= cur_peak * (1 - X / 100):
                in_pb = True
                trough = b["l"]
                pb_peak = cur_peak
        else:
            trough = min(trough, b["l"])
            if b["h"] > pb_peak:
                events.append(pb_peak)
                in_pb = False
                cur_peak = b["h"]
    # advances between consecutive recovered event peaks
    for a, b2 in zip(events, events[1:]):
        out.append((b2 / a - 1) * 100)
    return out


def main():
    trades = []
    for win, sc in WINDOWS.items():
        for t in json.load(open(os.path.join(sc, "res_cameron.json")))["items"]:
            t = dict(t)
            t["window"] = win
            trades.append(t)
    per_day = [(t, episodes_for(t)) for t in trades]
    all_eps = [(t, ep) for t, eps in per_day for ep in eps]

    L = [f"# Drawdown -> recovery curve (threshold-free) — {len(trades)} ticker-days,",
         f"  {len(all_eps)} retracement episodes (every dip below a running high counts).", ""]

    depths = [ep["depth"] for _, ep in all_eps]
    L.append("## A. Distribution of ALL retracement depths (no minimum)")
    L.append(f"   med {pctl(depths, .5):.2f}%  p75 {pctl(depths, .75):.2f}%  "
             f"p90 {pctl(depths, .9):.2f}%  p95 {pctl(depths, .95):.2f}%  "
             f"p99 {pctl(depths, .99):.2f}%  max {max(depths):.1f}%")
    L.append("   episodes per ticker-day reaching at least X%:")
    row = "   "
    for X in GRID:
        cnt = sum(1 for _, ep in all_eps if ep["depth"] >= X) / len(trades)
        row += f"  >={X}%:{cnt:.1f}"
    L.append(row)
    L.append("")

    L.append("## B. THE RECOVERY CURVE  P(new high | retracement reached >= X%)")
    L.append(f"   {'X%':>4} {'n_ev':>6} {'event-wtd':>10} {'95% CI':>15} "
             f"{'day-wtd':>8} {'n_days':>7} {'t.rec med':>10}")
    rng = random.Random(7)
    day_eps = [[ep for ep in eps] for _, eps in per_day]
    for X in GRID:
        qual = [(ti, ep) for ti, (_, eps) in enumerate(per_day) for ep in eps
                if ep["depth"] >= X]
        if len(qual) < 10:
            continue
        rec = sum(1 for _, ep in qual if ep["recovered"])
        p_ev = rec / len(qual)
        # day-weighted
        dvals = []
        for _, eps in per_day:
            q = [ep for ep in eps if ep["depth"] >= X]
            if q:
                dvals.append(sum(1 for ep in q if ep["recovered"]) / len(q))
        p_day = sum(dvals) / len(dvals)
        # cluster bootstrap over ticker-days
        boots = []
        for _ in range(1000):
            tot = recb = 0
            for _ in range(len(day_eps)):
                eps = day_eps[rng.randrange(len(day_eps))]
                for ep in eps:
                    if ep["depth"] >= X:
                        tot += 1
                        recb += ep["recovered"]
            if tot:
                boots.append(recb / tot)
        boots.sort()
        lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
        trec = [ep["rec_t"] - ep["cross_t"][X] for _, ep in qual
                if ep["recovered"] and X in ep["cross_t"]]
        L.append(f"   {X:>4} {len(qual):>6} {100 * p_ev:>9.1f}% "
                 f"[{100 * lo:>5.1f},{100 * hi:>5.1f}]% {100 * p_day:>7.1f}% "
                 f"{len(dvals):>7} {pctl(trec, .5) if trec else float('nan'):>9.0f}m")
    L.append("")

    L.append("## C. Conditional on NO recovery (terminal episode, depth >= X)")
    L.append(f"   {'X%':>4} {'n':>5} {'terminal depth med/p75':>24} {'close vs peak med':>19}")
    for X in GRID:
        fails = [ep for _, ep in all_eps if not ep["recovered"] and ep["depth"] >= X]
        if len(fails) < 5:
            continue
        dd = [ep["depth"] for ep in fails]
        cl = [(ep["close_px"] / ep["peak"] - 1) * 100 for ep in fails]
        L.append(f"   {X:>4} {len(fails):>5} {pctl(dd, .5):>12.1f}%/{pctl(dd, .75):.1f}% "
                 f"{pctl(cl, .5):>18.1f}%")
    L.append("")

    L.append("## D. After recovery at reporting scale X: next-leg advance")
    L.append("   (next >=X% retracement's peak vs the recovered peak)")
    for X in (2, 5, 8, 10, 15, 20):
        legs = [v for t in trades for v in scale_next_leg(t, X)]
        if len(legs) < 10:
            continue
        L.append(f"   X={X:>2}%: n={len(legs):>4}  advance med {pctl(legs, .5):+6.1f}%  "
                 f"p25 {pctl(legs, .25):+6.1f}%  p75 {pctl(legs, .75):+6.1f}%")
    L.append("")

    L.append("## E. Window split of the event-weighted curve")
    for win in ("OOS", "IS"):
        sub = [(t, ep) for t, ep in all_eps if t["window"] == win]
        row = f"   {win}: "
        for X in (2, 5, 8, 10, 15, 20):
            q = [ep for _, ep in sub if ep["depth"] >= X]
            if len(q) >= 10:
                row += f"X{X}:{100 * sum(e['recovered'] for e in q) / len(q):.0f}%({len(q)}) "
        L.append(row)

    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(HERE, "momentum_recovery_curve.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
