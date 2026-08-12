#!/usr/bin/env python3
"""Apply spec-v2 dip-conditioned take-profit exits to backtest entries.

Reads the entries produced by momentum_backtest.py (same entry logic as v1),
re-pulls each day's 1-min bars, and simulates the v2 exit rules from
momentum_spec_v2.md: no stop, take-profit ratcheting down with the running
post-entry dip, flat at 10:00 ET.

Reports the pre-registered pass/fail battery: slippage stress, top-5
exclusion, half-split, plus the untuned flat-target control.

Usage: MOMO_SCRATCH=... MOMO_TAG=oos python3 momentum_v2_exits.py
"""
import json
import os
from datetime import datetime

from momentum_paper import et_hhmm, et_offset, get, DATA

SCRATCH = os.environ["MOMO_SCRATCH"]
HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("MOMO_TAG", "v1")

# Spec v2, frozen: running dip below entry (%) -> take-profit target (%).
SCHEDULE = {0: 20, 2: 15, 5: 12, 10: 8, 20: 4}
THRESHOLDS = (20, 10, 5, 2)  # checked high-to-low
CONTROL = {0: 10, 2: 10, 5: 10, 10: 10, 20: 10}  # untuned baseline
CUTOFF = "10:00"


def day_bars(sym, day):
    off = et_offset(day)
    return get(
        f"{DATA}/v2/stocks/{sym}/bars",
        timeframe="1Min", adjustment="raw", feed="sip", limit=10000,
        start=f"{day}T{4 - off:02d}:00:00Z",
        end=f"{day}T{16 - off:02d}:00:00Z",
    ).get("bars") or []


def pctl(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def load_entries():
    """Cache post-entry bar paths so slippage variants don't re-fetch."""
    cache_path = os.path.join(SCRATCH, "v2_paths.json")
    if os.path.exists(cache_path):
        return json.load(open(cache_path))
    done = json.load(open(os.path.join(SCRATCH, "results.json")))
    out = []
    for t in done["items"]:
        if not t.get("exit_reason"):
            continue
        bars = day_bars(t["symbol"], t["day"])
        idx = next((i for i, b in enumerate(bars)
                    if et_hhmm(b["t"]) == t["entry_time_et"]), None)
        if idx is None:
            continue
        out.append({
            "symbol": t["symbol"], "day": t["day"],
            "entry_px_raw": t["entry_px_raw"],
            "path": [{"t": et_hhmm(b["t"]), "o": b["o"], "h": b["h"], "l": b["l"],
                      "c": b["c"]} for b in bars[idx:]],
        })
    json.dump(out, open(cache_path, "w"))
    return out


def simulate(entries, schedule, slip):
    rets = []
    for e in entries:
        raw = e["entry_px_raw"]
        fill = raw * (1 + slip)
        dip, tgt_pct, out = 0.0, schedule[0], None
        for b in e["path"]:
            if b["t"] >= CUTOFF:
                out = b["o"] * (1 - slip)
                break
            dip = max(dip, (1 - b["l"] / raw) * 100)
            for th in THRESHOLDS:
                if dip >= th:
                    tgt_pct = min(tgt_pct, schedule[th])
                    break
            target = raw * (1 + tgt_pct / 100)
            if b["h"] >= target:
                out = target  # resting limit
                break
        if out is None:
            out = e["path"][-1]["c"] * (1 - slip)
        rets.append({"symbol": e["symbol"], "day": e["day"],
                     "ret": (out / fill - 1) * 100})
    return rets


def summarize(rets):
    xs = [r["ret"] for r in rets]
    w = sum(1 for x in xs if x > 0)
    return (f"n={len(xs):>3} WR={100 * w / len(xs):>3.0f}% mean={sum(xs) / len(xs):+6.2f}% "
            f"med={pctl(xs, .5):+6.2f}% p25={pctl(xs, .25):+6.2f}% min={min(xs):+7.2f}%")


def main():
    entries = load_entries()
    L = [f"# Momentum spec-v2 exits — {TAG}", "",
         f"Entries: {len(entries)} (v1 entry logic, v2 exits per momentum_spec_v2.md)",
         f"Schedule: {SCHEDULE}  |  flat {CUTOFF} ET  |  no stop", ""]

    base = simulate(entries, SCHEDULE, 0.005)
    ctrl = simulate(entries, CONTROL, 0.005)
    L.append("## Headline (0.5%/side)")
    L.append(f"  v2 schedule : {summarize(base)}")
    L.append(f"  flat+10 ctrl: {summarize(ctrl)}")
    L.append("")

    L.append("## (b) Slippage stress")
    for s in (0.0025, 0.005, 0.01):
        L.append(f"  {s * 100:.2f}%/side: {summarize(simulate(entries, SCHEDULE, s))}")
    L.append("")

    by_sym = {}
    for r in base:
        by_sym.setdefault(r["symbol"], []).append(r["ret"])
    top5 = sorted(((sum(v), k) for k, v in by_sym.items()), reverse=True)[:5]
    excl = {k for _, k in top5}
    rest = [r for r in base if r["symbol"] not in excl]
    L.append("## (c) Concentration")
    L.append("  top-5 by summed return: "
             + ", ".join(f"{k} {v:+.1f}%" for v, k in top5))
    if rest:
        L.append(f"  excluding top-5: {summarize(rest)}")
    L.append("")

    days = sorted({r["day"] for r in base})
    mid = days[len(days) // 2] if days else None
    L.append("## (d) Half split")
    for lab, sel in (("H1", lambda r: r["day"] < mid),
                     ("H2", lambda r: r["day"] >= mid)):
        seg = [r for r in base if sel(r)]
        if seg:
            L.append(f"  {lab} (<{mid} / >=): {summarize(seg)}")
    L.append("")

    xs = [r["ret"] for r in base]
    checks = [
        ("a. mean > 0 @0.5%", sum(xs) / len(xs) > 0),
        ("b. mean > 0 @1.0%", (lambda v: sum(v) / len(v) > 0)(
            [r["ret"] for r in simulate(entries, SCHEDULE, 0.01)])),
        ("c. mean > 0 ex-top5", bool(rest) and
         sum(r["ret"] for r in rest) / len(rest) > 0),
        ("d. both halves > 0", all(
            sum(r["ret"] for r in seg) / len(seg) > 0
            for seg in ([r for r in base if r["day"] < mid],
                        [r for r in base if r["day"] >= mid]) if seg)),
        ("e. n >= 50", len(xs) >= 50),
    ]
    L.append("## Pre-registered criteria")
    for name, ok in checks:
        L.append(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    L.append("")
    L.append(f"ALL CRITERIA MET: {all(ok for _, ok in checks)}")

    out = "\n".join(L)
    print(out)
    with open(os.path.join(HERE, f"momentum_v2_{TAG}_results.md"), "w") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    main()
