#!/usr/bin/env python3
"""What separates the monsters? Forensics on post-target behaviour.

Clue from the winners table: stocks that went on to run huge barely pulled
back after the target filled (DFDV -6.3%, TRON +5.2%, OGEN -4.3%), while duds
gave back 30-50%. That argues for a TIGHT trailing stop on a runner tranche,
not the wide ones already tested (20-50%, all worse than selling out).

Sections:
  A. Does post-entry DIP DEPTH predict the size of the subsequent run?
  B. Tight trailing stops (3-15%) on a 25% runner.
  C. Other conditioners: entry time, relative volume, price, prior-day gap.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_runner_forensics.py
"""
import json
import os

from momentum_faithful import SCHEDULE, THRESHOLDS, FLAT, SLIP
from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCHES = {"OOS": os.environ["MOMO_OOS"], "IS": os.environ["MOMO_IS"]}


def load(scratch, first_only=False):
    items = json.load(open(os.path.join(scratch, "res_faithful.json")))["items"]
    if first_only:
        items = [x for x in items if x.get("n_dq_before", 0) == 0]
    return items


def target_fill(tr):
    """Walk to the target fill. Returns (idx, target_px, dip_at_fill) or None."""
    raw = tr["entry_px_raw"]
    dip, tgt = 0.0, SCHEDULE[0]
    for i, b in enumerate(tr["path"]):
        if b["t"] >= FLAT:
            return None
        dip = max(dip, (1 - b["l"] / raw) * 100)
        for th in THRESHOLDS:
            if dip >= th:
                tgt = min(tgt, SCHEDULE[th])
                break
        T = raw * (1 + tgt / 100)
        if b["h"] >= T:
            return i, T, dip
    return None


def run_with(tr, mode, frac=0.25, slip=SLIP):
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    tf = target_fill(tr)
    if tf is None:  # never reached target -> time/close exit on full size
        for b in tr["path"]:
            if b["t"] >= FLAT:
                return (b["o"] * (1 - slip) / fill - 1) * 100
        return (tr["path"][-1]["c"] * (1 - slip) / fill - 1) * 100
    i, T, _ = tf
    if mode is None:
        return (T / fill - 1) * 100
    proceeds = (1 - frac) * T
    rem, hi = frac, tr["path"][i]["h"]
    for b in tr["path"][i + 1:]:
        hi = max(hi, b["h"])
        if isinstance(mode, tuple):
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


def main():
    out = ["# Runner forensics — what separates the monsters", ""]
    allt = {k: load(v) for k, v in SCRATCHES.items()}
    pooled = allt["OOS"] + allt["IS"]

    # ---- A. dip depth vs subsequent run ----
    out.append("## A. Post-entry dip depth vs how far it ran AFTER the target filled")
    out.append("   (all faithful entries that reached their target)")
    out.append(f"   {'dip bucket':<16}{'n':>5}{'med run':>9}{'p75':>8}{'p90':>8}"
               f"{'max':>9}{'>50%':>7}{'med giveback':>14}")
    rows = []
    for t in pooled:
        tf = target_fill(t)
        if tf is None:
            continue
        i, T, dip = tf
        after = t["path"][i + 1:]
        if not after:
            continue
        runup = (max(b["h"] for b in after) / T - 1) * 100
        give = (min(b["l"] for b in after) / T - 1) * 100
        rows.append((dip, runup, give))
    buckets = [("no dip (<2%)", 0, 2), ("2-5%", 2, 5), ("5-10%", 5, 10),
               ("10-20%", 10, 20), (">=20%", 20, 999)]
    for lab, lo, hi in buckets:
        g = [r for r in rows if lo <= r[0] < hi]
        if not g:
            continue
        ru = sorted(r[1] for r in g)
        gv = sorted(r[2] for r in g)
        big = sum(1 for x in ru if x >= 50)
        out.append(f"   {lab:<16}{len(g):>5}{pctl(ru, .5):>+9.1f}{pctl(ru, .75):>+8.1f}"
                   f"{pctl(ru, .9):>+8.1f}{max(ru):>+9.1f}{100 * big / len(g):>6.0f}%"
                   f"{pctl(gv, .5):>+14.1f}")
    out.append("")

    # ---- B. tight trails ----
    out.append("## B. Trailing stop width on a 25% runner (mean %/trade, 0.5%/side)")
    modes = [("sell all (baseline)", None)] + \
            [(f"trail {p}%", ("trail", p / 100)) for p in (3, 5, 8, 10, 12, 15, 20)] + \
            [("flat 10:00", "flat10")]
    for setname, sel in (("ALL entries", False), ("1st-pullback only", True)):
        sets = {k: load(v, first_only=sel) for k, v in SCRATCHES.items()}
        pl = sets["OOS"] + sets["IS"]
        out.append(f"\n   {setname}: OOS n={len(sets['OOS'])} IS n={len(sets['IS'])} "
                   f"pooled n={len(pl)}")
        out.append(f"   {'variant':<22}{'OOS':>8}{'IS':>8}{'POOL':>8}"
                   f"{'pool@1%':>9}{'poolWR':>8}{'poolMax':>9}")
        for name, mode in modes:
            vals = {}
            for k in ("OOS", "IS"):
                r = [run_with(t, mode) for t in sets[k]]
                vals[k] = sum(r) / len(r) if r else float("nan")
            rp = [run_with(t, mode) for t in pl]
            rp10 = [run_with(t, mode, slip=0.01) for t in pl]
            w = sum(1 for v in rp if v > 0)
            out.append(f"   {name:<22}{vals['OOS']:>+8.2f}{vals['IS']:>+8.2f}"
                       f"{sum(rp) / len(rp):>+8.2f}{sum(rp10) / len(rp10):>+9.2f}"
                       f"{100 * w / len(rp):>7.0f}%{max(rp):>+9.1f}")
    out.append("")

    # ---- C. other conditioners on the run size ----
    out.append("## C. What else predicts a big run after the target?")
    feats = []
    for t in pooled:
        tf = target_fill(t)
        if tf is None:
            continue
        i, T, dip = tf
        after = t["path"][i + 1:]
        if not after:
            continue
        runup = (max(b["h"] for b in after) / T - 1) * 100
        hh, mm = t["entry_time_et"].split(":")
        feats.append({
            "runup": runup, "dip": dip,
            "entry_min": int(hh) * 60 + int(mm) - 420,
            "price": t["entry_px_raw"],
            "risk_pct": (t["entry_px_raw"] - t["stop"]) / t["entry_px_raw"] * 100,
            "n_dq": t.get("n_dq_before", 0),
        })
    for f in ("entry_min", "price", "risk_pct", "n_dq"):
        vals = sorted(feats, key=lambda x: x[f])
        q = len(vals) // 4
        out.append(f"   {f}:")
        for qi in range(4):
            seg = vals[qi * q:(qi + 1) * q if qi < 3 else len(vals)]
            ru = sorted(x["runup"] for x in seg)
            big = sum(1 for x in ru if x >= 50)
            out.append(f"     Q{qi + 1} [{seg[0][f]:.1f}..{seg[-1][f]:.1f}] n={len(seg)} "
                       f"med run {pctl(ru, .5):+.1f}%  p90 {pctl(ru, .9):+.1f}%  "
                       f">50%: {100 * big / len(seg):.0f}%")
    txt = "\n".join(out)
    print(txt)
    with open(os.path.join(HERE, "momentum_runner_forensics.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
