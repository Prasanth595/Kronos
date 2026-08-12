#!/usr/bin/env python3
"""Stepped (profit-scaled) trailing stop.

Rationale: a single tight trail protects the duds but strangles the runners,
which routinely pull back 10-20% mid-flight. A single wide trail lets runners
breathe but gives back too much on everything else. A STEPPED trail does both:
tight while the trade is unproven, progressively wider as profit accumulates.

Ladder form: [(profit_threshold_%, trail_%), ...] applied to the running
high; the widest tier whose threshold is met wins. Stop only ratchets up.
No initial stop (the grid search showed every fixed initial stop hurts).
Activation: the trail arms once price touches +ACT% above raw entry.

Selection on IS, verification on OOS. Fill degradation ("thru") applied to
every stop fill because tight trails are execution-sensitive.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_stepped_trail.py
"""
import json
import os

from momentum_exit_system import load, stats
from momentum_faithful import FLAT
from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
S_OOS, S_IS = os.environ["MOMO_OOS"], os.environ["MOMO_IS"]


def simulate(tr, ladder, act=4, slip=0.005, thru=0.02, cut=FLAT):
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    armed = False
    hi = None
    stop = None
    for b in tr["path"]:
        if cut != "close" and b["t"] >= cut:
            return (b["o"] * (1 - slip) / fill - 1) * 100
        if stop is not None and b["l"] <= stop:
            return (stop * (1 - thru) * (1 - slip) / fill - 1) * 100
        if not armed:
            if b["h"] >= raw * (1 + act / 100):
                armed = True
                hi = b["h"]
            else:
                continue
        else:
            hi = max(hi, b["h"])
        gain = (hi / raw - 1) * 100
        trail = ladder[0][1]
        for thr, tw in ladder:
            if gain >= thr:
                trail = tw
        cand = hi * (1 - trail / 100)
        stop = cand if stop is None else max(stop, cand)
    return (tr["path"][-1]["c"] * (1 - slip) / fill - 1) * 100


LADDERS = {
    "flat 3%":            [(0, 3)],
    "flat 8%":            [(0, 8)],
    "3->8 @10":           [(0, 3), (10, 8)],
    "3->10 @10":          [(0, 3), (10, 10)],
    "3->8@10->15@25":     [(0, 3), (10, 8), (25, 15)],
    "3->10@10->20@30":    [(0, 3), (10, 10), (30, 20)],
    "3->12@15->25@40":    [(0, 3), (15, 12), (40, 25)],
    "2->8@8->15@20":      [(0, 2), (8, 8), (20, 15)],
    "2->10@10->20@25->30@60": [(0, 2), (10, 10), (25, 20), (60, 30)],
    "5->15@20->30@50":    [(0, 5), (20, 15), (50, 30)],
    "3->8@10->15@25->25@50": [(0, 3), (10, 8), (25, 15), (50, 25)],
}

FILTERS = {
    "ALL": lambda x: True,
    "wide pullback (risk>=7.7%)":
        lambda x: (x["entry_px_raw"] - x["stop"]) / x["entry_px_raw"] * 100 >= 7.7,
    "price<8.3 & risk>=7.7":
        lambda x: x["entry_px_raw"] < 8.3
        and (x["entry_px_raw"] - x["stop"]) / x["entry_px_raw"] * 100 >= 7.7,
}


def main():
    IS, OOS = load(S_IS), load(S_OOS)
    L = ["# Stepped trailing stop", "",
         "No initial stop. Trail arms at +4%, widens as profit builds.",
         "Fills 0.5%/side, 2% slip through stops, flat 10:00 ET.", ""]
    for fname, f in FILTERS.items():
        i_, o = [x for x in IS if f(x)], [x for x in OOS if f(x)]
        p = i_ + o
        L.append(f"## {fname}  (IS {len(i_)}, OOS {len(o)}, pool {len(p)})")
        L.append(f"  {'ladder':<26}{'IS':>8}{'OOS':>8}{'POOL':>8}{'med':>7}"
                 f"{'p25':>7}{'p90':>8}{'max':>9}{'WR':>6}{'@5%thru':>9}")
        for lab, lad in LADDERS.items():
            ri = [simulate(x, lad) for x in i_]
            ro = [simulate(x, lad) for x in o]
            rp = [simulate(x, lad) for x in p]
            r5 = [simulate(x, lad, thru=0.05) for x in p]
            st = stats(rp)
            L.append(f"  {lab:<26}{sum(ri) / len(ri):>+8.2f}{sum(ro) / len(ro):>+8.2f}"
                     f"{st['mean']:>+8.2f}{st['med']:>+7.1f}{st['p25']:>+7.1f}"
                     f"{st['p90']:>+8.1f}{st['max']:>+9.1f}{st['wr']:>5.0f}%"
                     f"{sum(r5) / len(r5):>+9.2f}")
        L.append("")
    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(HERE, "momentum_stepped_trail_results.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
