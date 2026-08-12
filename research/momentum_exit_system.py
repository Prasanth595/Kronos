#!/usr/bin/env python3
"""Exit-system search: initial stop x trail activation x trail width.

Structure per trade (all levels measured off the RAW entry price):
  1. INITIAL STOP at -S% until the trade proves itself.
  2. ACTIVATION at +A% (or the v2 dip-conditioned level): once the high
     touches it, the stop converts to a TRAILING stop.
  3. TRAIL of T% below the running high thereafter. Stop only ratchets up.
  4. Time exit at 10:00 ET (or close).

Selection protocol to limit multiple-comparison damage:
  - The grid is scored on the IS window ONLY (2025-08..2026-08), which is
    already in-sample for the v2 schedule.
  - The chosen config is then reported on OOS (2024-08..2025-08) untouched
    by selection, and must hold up there to count.
  - Every result is re-run with fill degradation ("thru") because a tight
    trail is the most execution-sensitive thing in this whole project.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_exit_system.py
"""
import json
import os

from momentum_faithful import SCHEDULE, THRESHOLDS, FLAT
from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
S_OOS, S_IS = os.environ["MOMO_OOS"], os.environ["MOMO_IS"]


def load(scratch, first_only=False):
    it = json.load(open(os.path.join(scratch, "res_faithful.json")))["items"]
    return [x for x in it if x.get("n_dq_before", 0) == 0] if first_only else it


def simulate(tr, stop_pct, act, trail, slip=0.005, thru=0.0, cut=FLAT):
    """stop_pct: initial stop % below entry (None = no stop).
       act: activation as % above entry, or 'dip' for the v2 schedule level.
       trail: trailing % below running high (None = sell at activation)."""
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    stop = raw * (1 - stop_pct / 100) if stop_pct is not None else None
    armed = False
    hi = None
    dip, tgt = 0.0, SCHEDULE[0]

    def out(px):
        return (px / fill - 1) * 100

    for b in tr["path"]:
        if cut != "close" and b["t"] >= cut:
            return out(b["o"] * (1 - slip))
        # stop check first (conservative: adverse before favourable)
        if stop is not None and b["l"] <= stop:
            return out(stop * (1 - thru) * (1 - slip))
        if not armed:
            if act == "dip":
                dip = max(dip, (1 - b["l"] / raw) * 100)
                for th in THRESHOLDS:
                    if dip >= th:
                        tgt = min(tgt, SCHEDULE[th])
                        break
                lvl = raw * (1 + tgt / 100)
            else:
                lvl = raw * (1 + act / 100)
            if b["h"] >= lvl:
                if trail is None:
                    return out(lvl)          # plain target sale
                armed = True
                hi = b["h"]
                stop = max(stop or 0, hi * (1 - trail / 100))
            continue
        hi = max(hi, b["h"])
        stop = max(stop, hi * (1 - trail / 100))
    return out(tr["path"][-1]["c"] * (1 - slip))


def stats(rs):
    rs = sorted(rs)
    w = sum(1 for x in rs if x > 0)
    return {"n": len(rs), "wr": 100 * w / len(rs), "mean": sum(rs) / len(rs),
            "med": pctl(rs, .5), "p10": pctl(rs, .1), "p25": pctl(rs, .25),
            "p75": pctl(rs, .75), "p90": pctl(rs, .9), "max": max(rs),
            "min": min(rs)}


def main():
    IS, OOS = load(S_IS), load(S_OOS)
    STOPS = [None, 20, 15, 12, 10, 8, 6]
    ACTS = ["dip", 4, 6, 8, 10, 15]
    TRAILS = [None, 2, 3, 5, 8, 12]
    THRU = 0.02  # realistic-ish default for the search

    grid = []
    for s in STOPS:
        for a in ACTS:
            for t in TRAILS:
                r_is = [simulate(x, s, a, t, thru=THRU) for x in IS]
                st = stats(r_is)
                grid.append((st["mean"], s, a, t, st))
    grid.sort(reverse=True, key=lambda g: g[0])

    L = ["# Exit-system search (initial stop x activation x trail)", "",
         f"Scored on IS n={len(IS)}; OOS n={len(OOS)} held out of selection.",
         f"Fills: 0.5%/side + {THRU * 100:.0f}% slip through stops. Flat 10:00 ET.", "",
         "## Top 15 configurations by IS mean"]
    L.append(f"  {'stop':>6}{'act':>6}{'trail':>7}{'IS mean':>9}{'IS med':>8}"
             f"{'IS WR':>7}{'OOS mean':>10}{'OOS med':>9}{'OOS WR':>8}{'OOSp10':>8}")
    for mean, s, a, t, st in grid[:15]:
        ro = stats([simulate(x, s, a, t, thru=THRU) for x in OOS])
        L.append(f"  {str(s):>6}{str(a):>6}{str(t):>7}{mean:>+9.2f}{st['med']:>+8.1f}"
                 f"{st['wr']:>6.0f}%{ro['mean']:>+10.2f}{ro['med']:>+9.1f}"
                 f"{ro['wr']:>7.0f}%{ro['p10']:>+8.1f}")

    # the selected config = best on IS
    _, bs, ba, bt, _ = grid[0]
    L.append(f"\n## SELECTED ON IS: stop {bs}, activation {ba}, trail {bt}")
    L.append(f"  {'window':<8}{'n':>5}{'WR':>6}{'mean':>9}{'p10':>8}{'p25':>8}"
             f"{'med':>8}{'p75':>8}{'p90':>8}{'max':>9}{'min':>9}")
    for lab, ds in (("IS", IS), ("OOS", OOS), ("POOL", IS + OOS)):
        st = stats([simulate(x, bs, ba, bt, thru=THRU) for x in ds])
        L.append(f"  {lab:<8}{st['n']:>5}{st['wr']:>5.0f}%{st['mean']:>+9.2f}"
                 f"{st['p10']:>+8.1f}{st['p25']:>+8.1f}{st['med']:>+8.1f}"
                 f"{st['p75']:>+8.1f}{st['p90']:>+8.1f}{st['max']:>+9.1f}{st['min']:>+9.1f}")

    L.append("\n## Robustness of the selected config")
    L.append(f"  {'variant':<28}{'IS':>9}{'OOS':>9}{'POOL':>9}")
    for lab, kw in (("0.5% slip, 0% thru", dict(slip=.005, thru=0)),
                    ("0.5% slip, 2% thru", dict(slip=.005, thru=.02)),
                    ("0.5% slip, 5% thru", dict(slip=.005, thru=.05)),
                    ("1.0% slip, 2% thru", dict(slip=.01, thru=.02)),
                    ("1.0% slip, 5% thru", dict(slip=.01, thru=.05)),
                    ("hold to close, 2% thru", dict(slip=.005, thru=.02, cut="close"))):
        vals = [sum(simulate(x, bs, ba, bt, **kw) for x in ds) / len(ds)
                for ds in (IS, OOS, IS + OOS)]
        L.append(f"  {lab:<28}{vals[0]:>+9.2f}{vals[1]:>+9.2f}{vals[2]:>+9.2f}")

    # neighbourhood: is the peak a spike or a plateau?
    L.append("\n## Neighbourhood of the selection (POOL mean, 2% thru)")
    L.append("  " + "stop/trail".ljust(12) + "".join(f"{str(t):>8}" for t in TRAILS))
    for s in STOPS:
        row = []
        for t in TRAILS:
            r = [simulate(x, s, ba, t, thru=THRU) for x in IS + OOS]
            row.append(sum(r) / len(r))
        L.append(f"  {str(s):<12}" + "".join(f"{v:>+8.2f}" for v in row))

    # first-pullback subset under the selected config
    L.append("\n## Selected config on 1st-pullback entries only")
    for lab, sc in (("IS", S_IS), ("OOS", S_OOS)):
        g = load(sc, first_only=True)
        st = stats([simulate(x, bs, ba, bt, thru=THRU) for x in g])
        L.append(f"  {lab}: n={st['n']} WR={st['wr']:.0f}% mean={st['mean']:+.2f}% "
                 f"med={st['med']:+.1f}% p10={st['p10']:+.1f}% max={st['max']:+.1f}%")

    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(HERE, "momentum_exit_system_results.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
