#!/usr/bin/env python3
"""Spec-v3 laddered scale-out with ratcheting stop, plus v2 and control.

Runs every pre-registered exit scheme over the SAME entries so the comparison
is like-for-like, and prints the pass/fail battery for each.

Usage: MOMO_SCRATCH=... MOMO_TAG=oos python3 momentum_v3_exits.py
"""
import json
import os

from momentum_v2_exits import (SCHEDULE, THRESHOLDS, CONTROL, CUTOFF,
                               load_entries, pctl, simulate as simulate_v2)

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("MOMO_TAG", "v1")

BASECAMPS = (5, 10, 20, 35)  # % above raw entry
TRANCHE = 0.25
RATCHET = {0: None, 1: 0.0, 2: 5.0, 3: 10.0, 4: 20.0}  # crossings -> stop %


def simulate_v3(entries, slip, initial_stop=None, dip_conditioned=False):
    """initial_stop: None (hold through dip) or 'pullback' (v1 stop)."""
    out_rows = []
    for e in entries:
        raw = e["entry_px_raw"]
        fill = raw * (1 + slip)
        stop_px = e.get("stop") if initial_stop == "pullback" else None
        crossed = 0
        remaining = 1.0
        proceeds = 0.0
        dip = 0.0
        for b in e["path"]:
            if b["t"] >= CUTOFF:
                proceeds += remaining * b["o"] * (1 - slip)
                remaining = 0.0
                break
            # 1) stop first (conservative), at the level in force entering the bar
            if stop_px is not None and b["l"] <= stop_px:
                proceeds += remaining * stop_px * 0.99 * (1 - slip)
                remaining = 0.0
                break
            dip = max(dip, (1 - b["l"] / raw) * 100)
            # 2) basecamp crossings
            while crossed < len(BASECAMPS) and remaining > 1e-9:
                lvl = BASECAMPS[crossed]
                if dip_conditioned and dip >= 10:
                    lvl = lvl / 2.0
                target = raw * (1 + lvl / 100)
                if b["h"] < target:
                    break
                sell = min(TRANCHE, remaining)
                proceeds += sell * target
                remaining -= sell
                crossed += 1
                r = RATCHET[crossed]
                if r is not None:
                    lvl_stop = raw * (1 + r / 100)
                    stop_px = lvl_stop if stop_px is None else max(stop_px, lvl_stop)
            if remaining <= 1e-9:
                break
        if remaining > 1e-9:
            proceeds += remaining * e["path"][-1]["c"] * (1 - slip)
        out_rows.append({"symbol": e["symbol"], "day": e["day"],
                         "ret": (proceeds / fill - 1) * 100})
    return out_rows


def summarize(rets):
    xs = [r["ret"] for r in rets]
    w = sum(1 for x in xs if x > 0)
    return (f"n={len(xs):>3} WR={100 * w / len(xs):>3.0f}% mean={sum(xs) / len(xs):+6.2f}% "
            f"med={pctl(xs, .5):+6.2f}% p25={pctl(xs, .25):+6.2f}% min={min(xs):+7.2f}%")


def battery(entries, fn, L, name):
    base = fn(0.005)
    xs = [r["ret"] for r in base]
    hi = [r["ret"] for r in fn(0.01)]
    by_sym = {}
    for r in base:
        by_sym.setdefault(r["symbol"], []).append(r["ret"])
    top5 = {k for _, k in sorted(((sum(v), k) for k, v in by_sym.items()),
                                 reverse=True)[:5]}
    rest = [r for r in base if r["symbol"] not in top5]
    days = sorted({r["day"] for r in base})
    mid = days[len(days) // 2]
    halves = [[r for r in base if r["day"] < mid],
              [r for r in base if r["day"] >= mid]]
    checks = [
        ("a mean>0 @0.5%", sum(xs) / len(xs) > 0),
        ("b mean>0 @1.0%", sum(hi) / len(hi) > 0),
        ("c ex-top5>0", bool(rest) and sum(r["ret"] for r in rest) / len(rest) > 0),
        ("d halves>0", all(sum(r["ret"] for r in h) / len(h) > 0 for h in halves if h)),
        ("e n>=50", len(xs) >= 50),
    ]
    L.append(f"### {name}")
    L.append(f"  0.5%/side : {summarize(base)}")
    L.append(f"  1.0%/side : {summarize(fn(0.01))}")
    if rest:
        L.append(f"  ex-top5   : {summarize(rest)}")
    for i, h in enumerate(halves, 1):
        if h:
            L.append(f"  H{i}        : {summarize(h)}")
    L.append("  " + "  ".join(f"[{'P' if ok else 'F'}] {n}" for n, ok in checks))
    L.append(f"  ALL PASS: {all(ok for _, ok in checks)}")
    L.append("")
    return all(ok for _, ok in checks)


def main():
    entries = load_entries()
    L = [f"# Momentum exit-scheme comparison — {TAG}", "",
         f"Entries: {len(entries)} (identical across all schemes; v1 entry logic)",
         f"Ladder {BASECAMPS} @ {int(TRANCHE * 100)}% each, ratchet {RATCHET}, "
         f"flat {CUTOFF} ET", ""]

    schemes = [
        ("v3-nostop (PRIMARY)", lambda s: simulate_v3(entries, s)),
        ("v3-pbstop", lambda s: simulate_v3(entries, s, initial_stop="pullback")),
        ("v3-dipcond", lambda s: simulate_v3(entries, s, dip_conditioned=True)),
        ("v2 dip-conditioned target", lambda s: simulate_v2(entries, SCHEDULE, s)),
        ("control flat +10%", lambda s: simulate_v2(entries, CONTROL, s)),
    ]
    verdicts = {}
    for name, fn in schemes:
        verdicts[name] = battery(entries, fn, L, name)

    L.append("## Summary")
    for name, ok in verdicts.items():
        L.append(f"  {'PASS' if ok else 'fail'}  {name}")

    out = "\n".join(L)
    print(out)
    with open(os.path.join(HERE, f"momentum_v3_{TAG}_results.md"), "w") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    main()
