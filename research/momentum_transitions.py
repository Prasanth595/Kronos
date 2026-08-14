#!/usr/bin/env python3
"""Post-entry state-sequence analysis on the CORRECTED Cameron entries.

Descriptive only: transition probabilities and movement percentiles.
No thresholds are searched, no exits simulated, no subsets optimized.

State machine (measurement convention, declared not optimized):
  EXPANSION: price tracking its running high (from the entry bar onward).
  PULLBACK k: begins when price first trades >= T% below the running high
              (T = 5% main tables; T = 8% sensitivity line).
  RECOVERY:  the pullback resolves when price exceeds the pre-pullback peak
             (a NEW HIGH). If the close arrives first, the pullback FAILED.
All prices relative to the raw entry price; times in minutes after entry.
Full session used (entry -> 16:00) so afternoon behaviour is visible.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_transitions.py
"""
import json
import os

from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = {"OOS": os.environ["MOMO_OOS"], "IS": os.environ["MOMO_IS"]}


def tmin(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def load():
    out = []
    for win, sc in WINDOWS.items():
        for t in json.load(open(os.path.join(sc, "res_cameron.json")))["items"]:
            t = dict(t)
            t["window"] = win
            out.append(t)
    return out


def sequence(t, T):
    """Decompose one path into expansion/pullback events."""
    e = t["entry_px_raw"]
    path = t["path"]
    t0 = tmin(path[0]["t"])
    run_max, run_t = path[0]["h"], 0
    events = []
    cur = None  # active pullback dict
    for b in path:
        mt = tmin(b["t"]) - t0
        if cur is None:
            if b["h"] > run_max:
                run_max, run_t = b["h"], mt
            if b["l"] <= run_max * (1 - T / 100):
                cur = {"peak": run_max, "peak_pct": (run_max / e - 1) * 100,
                       "peak_t": run_t, "start_t": mt,
                       "trough": b["l"], "trough_t": mt}
        else:
            if b["l"] < cur["trough"]:
                cur["trough"], cur["trough_t"] = b["l"], mt
            if b["h"] > cur["peak"]:
                cur["recovered"] = True
                cur["rec_t"] = mt
                events.append(cur)
                run_max, run_t = b["h"], mt
                cur = None
    if cur is not None:
        cur["recovered"] = False
        cur["close_px"] = path[-1]["c"]
        events.append(cur)
    for k, ev in enumerate(events, 1):
        ev["k"] = k
        ev["depth_pct"] = (ev["peak"] - ev["trough"]) / ev["peak"] * 100
    # expansion sizes: entry->peak1, trough_k->peak_{k+1}
    exps = []
    if events:
        exps.append({"k": 1, "gain_pct": (events[0]["peak"] / e - 1) * 100,
                     "dur": events[0]["peak_t"]})
        for k in range(1, len(events)):
            if events[k - 1]["recovered"]:
                exps.append({"k": k + 1,
                             "gain_pct": (events[k]["peak"] / events[k - 1]["trough"] - 1) * 100,
                             "dur": events[k]["peak_t"] - events[k - 1]["trough_t"]})
    return events, exps


def first_touch_race(trades):
    LV = [2, 5, 10, -2, -5, -10]
    counts = {lv: 0 for lv in LV}
    counts["ambiguous"] = 0
    counts["none"] = 0
    for t in trades:
        e = t["entry_px_raw"]
        first = None
        for b in t["path"]:
            up = [lv for lv in LV if lv > 0 and b["h"] >= e * (1 + lv / 100)]
            dn = [lv for lv in LV if lv < 0 and b["l"] <= e * (1 + lv / 100)]
            if up and dn:
                first = "ambiguous"
                break
            if up:
                first = min(up)   # smallest positive level crossed first
                break
            if dn:
                first = max(dn)   # shallowest negative level
                break
        counts[first if first is not None else "none"] += 1
    return counts


def after_level(trades, lv, target, floor):
    """Among trades touching +lv%: race from that moment between +target%
    and a fall to floor% (0 = back to entry)."""
    n = hit_t = hit_f = neither = 0
    for t in trades:
        e = t["entry_px_raw"]
        i0 = next((i for i, b in enumerate(t["path"])
                   if b["h"] >= e * (1 + lv / 100)), None)
        if i0 is None:
            continue
        n += 1
        res = None
        for b in t["path"][i0 + 1:]:
            u = b["h"] >= e * (1 + target / 100)
            d = b["l"] <= e * (1 + floor / 100)
            if u and d:
                res = "f"  # conservative: adverse first
                break
            if u:
                res = "t"
                break
            if d:
                res = "f"
                break
        if res == "t":
            hit_t += 1
        elif res == "f":
            hit_f += 1
        else:
            neither += 1
    return n, hit_t, hit_f, neither


def main():
    trades = load()
    L = [f"# Post-entry state sequences — corrected Cameron entries (n={len(trades)})",
         "Pullback threshold T=5% of the running high (measurement convention).",
         "All figures descriptive; nothing optimized.", ""]

    # 1. first-touch race
    L.append("## 1. First level touched after entry (race among +-2/5/10%)")
    c = first_touch_race(trades)
    n = len(trades)
    for k in (2, 5, 10, -2, -5, -10, "ambiguous", "none"):
        L.append(f"   first touch {str(k):>10}: {c[k]:>4}  ({100 * c[k] / n:.0f}%)")
    L.append("")

    # 2/3. conditional races
    L.append("## 2. Conditional races (u/d same bar counted adverse)")
    for lv, tgt, fl in ((5, 10, 0), (10, 20, 0), (10, 15, 5), (2, 5, -2)):
        nn, ht, hf, ne = after_level(trades, lv, tgt, fl)
        L.append(f"   reached +{lv}% (n={nn}): next +{tgt}% first {100 * ht / nn:.0f}% | "
                 f"fell to {fl:+d}% first {100 * hf / nn:.0f}% | neither {100 * ne / nn:.0f}%")
    L.append("")

    # sequence decomposition at T=5
    T = 5
    per_k = {}
    exp_k = {}
    n_events = []
    for t in trades:
        evs, exps = sequence(t, T)
        n_events.append(sum(1 for e in evs))
        for e in evs:
            per_k.setdefault(min(e["k"], 4), []).append(e)
        for x in exps:
            exp_k.setdefault(min(x["k"], 4), []).append(x)

    L.append(f"## 3. How many >={T}% pullbacks occur per ticker-day")
    for i in range(0, 7):
        cnt = sum(1 for x in n_events if x == i)
        if cnt:
            L.append(f"   {i} pullbacks: {cnt:>4} ({100 * cnt / len(trades):.0f}%)")
    L.append(f"   mean {sum(n_events) / len(trades):.1f} pullback events/day")
    L.append("")

    L.append("## 4. Expansion legs (size of each squeeze)")
    L.append("   leg 1 = entry->first peak; leg k = trough(k-1)->peak k")
    for k in sorted(exp_k):
        g = [x["gain_pct"] for x in exp_k[k]]
        d = [x["dur"] for x in exp_k[k]]
        lab = f"{k}" if k < 4 else "4+"
        L.append(f"   leg {lab}: n={len(g):>3}  gain med {pctl(g, .5):+6.1f}%  "
                 f"p25 {pctl(g, .25):+6.1f}%  p75 {pctl(g, .75):+6.1f}%  "
                 f"dur med {pctl(d, .5):.0f}min")
    L.append("")

    L.append("## 5. Pullback events by order (the transition table)")
    L.append(f"   {'PB#':<5}{'n':>4}{'P(new high)':>12}{'depth med':>11}{'p25':>7}"
             f"{'p75':>7}{'peak@ med':>10}{'t.peak':>8}{'t.rec':>7}")
    for k in sorted(per_k):
        evs = per_k[k]
        rec = [e for e in evs if e["recovered"]]
        dep = [e["depth_pct"] for e in evs]
        pk = [e["peak_pct"] for e in evs]
        tp = [e["peak_t"] for e in evs]
        tr = [e["rec_t"] - e["start_t"] for e in rec]
        lab = f"{k}" if k < 4 else "4+"
        L.append(f"   {lab:<5}{len(evs):>4}{100 * len(rec) / len(evs):>11.0f}%"
                 f"{pctl(dep, .5):>10.1f}%{pctl(dep, .25):>6.1f}%{pctl(dep, .75):>6.1f}%"
                 f"{pctl(pk, .5):>+9.1f}%{pctl(tp, .5):>7.0f}m{pctl(tr, .5) if tr else float('nan'):>6.0f}m")
    L.append("   (depth = % off the peak; peak@ = peak level vs entry; t.peak =")
    L.append("   minutes entry->peak; t.rec = minutes pullback-start->new high)")
    L.append("")

    L.append("## 6. Failed pullbacks: where they end up")
    for k in sorted(per_k):
        fails = [e for e in per_k[k] if not e["recovered"]]
        if not fails:
            continue
        dep = [e["depth_pct"] for e in fails]
        lab = f"{k}" if k < 4 else "4+"
        L.append(f"   PB{lab} failures n={len(fails)}: depth by close med "
                 f"{pctl(dep, .5):.1f}% p75 {pctl(dep, .75):.1f}% max {max(dep):.1f}%")
    L.append("")

    L.append("## 7. Path dependence checks")
    # does PB1 depth predict PB2 recovery?
    pb2 = per_k.get(2, [])
    if pb2:
        # link back: need PB1 depth per trade; rebuild quickly
        deep, shallow = [], []
        for t in trades:
            evs, _ = sequence(t, T)
            if len(evs) >= 2 and evs[0]["recovered"]:
                (deep if evs[0]["depth_pct"] >= 8 else shallow).append(evs[1])
        for lab, g in (("PB1 shallow (<8%)", shallow), ("PB1 deep (>=8%)", deep)):
            if g:
                r = sum(1 for e in g if e["recovered"])
                L.append(f"   P(PB2 new high | {lab}): {100 * r / len(g):.0f}%  (n={len(g)})")
    # time-of-day deterioration
    L.append("   P(new high) by pullback START time (all PB orders):")
    allev = [e for v in per_k.values() for e in v]
    for lo, hi, lab in ((0, 60, "0-60min"), (60, 120, "60-120"), (120, 240, "120-240"),
                        (240, 600, "240+")):
        g = [e for e in allev if lo <= e["start_t"] < hi]
        if g:
            r = sum(1 for e in g if e["recovered"])
            L.append(f"     start {lab:>8}: {100 * r / len(g):>3.0f}%  (n={len(g)})")
    L.append("")

    # sensitivity at T=8
    per_k8 = {}
    for t in trades:
        evs, _ = sequence(t, 8)
        for e in evs:
            per_k8.setdefault(min(e["k"], 4), []).append(e)
    L.append("## 8. Sensitivity: same transition probs at T=8%")
    for k in sorted(per_k8):
        evs = per_k8[k]
        r = sum(1 for e in evs if e["recovered"])
        lab = f"{k}" if k < 4 else "4+"
        L.append(f"   PB{lab}: n={len(evs):>3}  P(new high) {100 * r / len(evs):.0f}%")
    L.append("")

    # window stability of headline transitions
    L.append("## 9. Window stability (T=5%)")
    for win in ("OOS", "IS"):
        sub = [t for t in trades if t["window"] == win]
        pk = {}
        for t in sub:
            evs, _ = sequence(t, T)
            for e in evs:
                pk.setdefault(min(e["k"], 4), []).append(e)
        line = f"   {win}: "
        for k in sorted(pk):
            evs = pk[k]
            r = sum(1 for e in evs if e["recovered"])
            line += f"PB{k if k < 4 else '4+'} {100 * r / len(evs):.0f}% (n={len(evs)})  "
        L.append(line)

    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(HERE, "momentum_transitions.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
