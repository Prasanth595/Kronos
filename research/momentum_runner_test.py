#!/usr/bin/env python3
"""Runner-tranche test on first-pullback entries.

Question: 49/53 winners kept rising after the v2 target filled (avg +53.6%
further). Can any part of that be captured by letting a fraction ride?

Sells (1-F) of the position at the v2 dip-conditioned target, then holds the
remaining F under one of several rules:
  trail X%   - trailing stop X% below the running high, until 10:00 or close
  flat10     - hold to the 10:00 ET time exit
  close      - hold to the 16:00 close

Baseline is v2 with the whole position sold at the target.
Run on 1st-pullback entries only (n_dq_before == 0), per window and pooled.

Usage: MOMO_SCRATCH=<any> python3 momentum_runner_test.py
"""
import json
import os

from momentum_faithful import SCHEDULE, THRESHOLDS, FLAT, SLIP
from momentum_v2_exits import pctl

B = os.environ.get("MOMO_BASE", os.path.dirname(os.path.abspath(__file__)))
SCRATCHES = {"OOS": os.environ["MOMO_OOS"], "IS": os.environ["MOMO_IS"]}


def entries(scratch):
    items = json.load(open(os.path.join(scratch, "res_faithful.json")))["items"]
    return [x for x in items if x.get("n_dq_before", 0) == 0]


def run(tr, mode, frac=0.25, slip=SLIP):
    """mode: None (sell all), ('trail', pct), 'flat10', 'close'."""
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    dip, tgt = 0.0, SCHEDULE[0]
    proceeds, rem, hi = 0.0, 1.0, None
    filled = False
    for b in tr["path"]:
        if not filled:
            if b["t"] >= FLAT:                      # target never hit
                proceeds += rem * b["o"] * (1 - slip)
                rem = 0.0
                break
            dip = max(dip, (1 - b["l"] / raw) * 100)
            for th in THRESHOLDS:
                if dip >= th:
                    tgt = min(tgt, SCHEDULE[th])
                    break
            T = raw * (1 + tgt / 100)
            if b["h"] >= T:
                if mode is None:
                    proceeds += rem * T
                    rem = 0.0
                    break
                proceeds += (1 - frac) * T
                rem = frac
                hi = b["h"]
                filled = True
            continue
        # runner leg
        hi = max(hi, b["h"])
        if isinstance(mode, tuple):                 # trailing stop
            stop = hi * (1 - mode[1])
            if b["l"] <= stop:
                proceeds += rem * stop * (1 - slip)
                rem = 0.0
                break
        if mode == "flat10" and b["t"] >= FLAT:
            proceeds += rem * b["o"] * (1 - slip)
            rem = 0.0
            break
    if rem > 0:
        proceeds += rem * tr["path"][-1]["c"] * (1 - slip)
    return (proceeds / fill - 1) * 100


MODES = [
    ("v2 sell all (baseline)", None),
    ("25% runner, trail 20%", ("trail", 0.20)),
    ("25% runner, trail 30%", ("trail", 0.30)),
    ("25% runner, trail 40%", ("trail", 0.40)),
    ("25% runner, trail 50%", ("trail", 0.50)),
    ("25% runner, flat 10:00", "flat10"),
    ("25% runner, to close", "close"),
]


def report(label, trades, out):
    out.append(f"\n### {label}  (n={len(trades)})")
    out.append(f"  {'variant':<26}{'WR':>5}{'p25':>8}{'med':>8}{'p75':>8}"
               f"{'p90':>8}{'max':>9}{'mean':>8}{'@1%':>8}")
    for name, mode in MODES:
        r = sorted(run(t, mode) for t in trades)
        r10 = [run(t, mode, slip=0.01) for t in trades]
        w = sum(1 for v in r if v > 0)
        out.append(f"  {name:<26}{100 * w / len(r):>4.0f}%"
                   + "".join(f"{pctl(r, q):>+8.1f}" for q in (.25, .5, .75, .9))
                   + f"{max(r):>+9.1f}{sum(r) / len(r):>+8.2f}"
                   + f"{sum(r10) / len(r10):>+8.2f}")


def main():
    out = ["# Runner-tranche test — first-pullback entries only",
           "Sell 75% at the v2 dip-conditioned target; the last 25% rides.",
           "All figures %/trade after 0.5%/side slippage (last column 1.0%)."]
    pooled = []
    for tag, sc in SCRATCHES.items():
        e = entries(sc)
        pooled += e
        report(tag, e, out)
    report("POOLED OOS+IS", pooled, out)
    txt = "\n".join(out)
    print(txt)
    with open(os.path.join(B, "momentum_runner_results.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
