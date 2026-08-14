#!/usr/bin/env python3
"""Regenerate the v5 per-trade roster from the faithful-engine results.

Loads res_faithful.json from the IS and OOS scratch dirs, applies the v5
selection filter (pullback width >= 8%, entry < $8.30) and the v5 exit
(momentum_live.v5_exit), and writes the full trade-by-trade table to
momentum_v5_trades.md.
"""
import json
import os

from momentum_live import v5_exit, MIN_RISK_PCT, MAX_PRICE

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ["MOMO_BASE"]  # dir containing momo_f_is/ and momo_f_oos/


def load(window):
    p = os.path.join(BASE, f"momo_f_{window}", "res_faithful.json")
    return json.load(open(p))["items"]


rows = []
for window in ("is", "oos"):
    for t in load(window):
        risk = (t["entry_px_raw"] - t["stop"]) / t["entry_px_raw"] * 100
        if risk < MIN_RISK_PCT or t["entry_px_raw"] >= MAX_PRICE:
            continue
        ret, xt, reason = v5_exit(t)
        rows.append({"window": window.upper(), "symbol": t["symbol"],
                     "day": t["day"], "in_t": t["entry_time_et"],
                     "in_px": t["entry_px_raw"], "width": round(risk, 1),
                     "out_t": xt, "reason": reason, "ret": round(ret, 2)})

rows.sort(key=lambda r: (r["day"], r["in_t"]))
L = ["# Momentum v5 — full trade roster (regenerated)", "",
     "Selection: pullback width >= 8% of entry AND entry < $8.30.",
     "Exit: no stop; trail arms at +2%, 0.25 x ATR(14,1m); flat 10:00 ET.",
     "Fills: entry +0.5%, trail-stop 2% through +0.5%, time exit -0.5%.", "",
     "| # | Window | Symbol | Date | Entry | Px | Width% | Exit | Reason | Ret% |",
     "|---|--------|--------|------|-------|-----|--------|------|--------|------|"]
for i, r in enumerate(rows, 1):
    L.append(f"| {i} | {r['window']} | {r['symbol']} | {r['day']} | {r['in_t']} | "
             f"{r['in_px']:.2f} | {r['width']} | {r['out_t']} | {r['reason']} | "
             f"{r['ret']:+.2f} |")

for w in ("IS", "OOS", None):
    seg = [r for r in rows if w is None or r["window"] == w]
    if not seg:
        continue
    rets = sorted(r["ret"] for r in seg)
    wins = sum(1 for r in seg if r["ret"] > 0)
    lab = w or "POOL"
    L.append("")
    L.append(f"**{lab}**: n={len(seg)}, WR={100 * wins / len(seg):.0f}%, "
             f"mean={sum(rets) / len(rets):+.2f}%, median={rets[len(rets) // 2]:+.2f}%, "
             f"worst={rets[0]:+.2f}%, best={rets[-1]:+.2f}%")

out = "\n".join(L)
print(out)
open(os.path.join(HERE, "momentum_v5_trades.md"), "w").write(out + "\n")
