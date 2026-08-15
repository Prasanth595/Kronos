#!/usr/bin/env python3
"""Spec v6 simulator — junction-process policy (momentum_spec_v6.md, frozen).

Consumes res_cameron.json entry records (the qualification event and the
bar path from that moment). Implements: arm at -10% from running high,
confirmation entry (prior-bar-high break), exit at -10% from post-entry
high, abandon at -25%, size cut after >=20% junctions, max 4 entries,
flat at close. Parameters are the frozen spec's; none are configurable
except slip-through for the mandated sensitivity report.

Usage: MOMO_SCRATCHES="name1=path1,name2=path2" python3 momentum_v6.py
"""
import json
import os

from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))

ARM = 0.10       # junction depth that arms entry / triggers exit
ABANDON = 0.25   # done-for-the-day depth
SIZE_CUT_DEPTH = 0.20
MAX_ENTRIES = 4
SLIP = 0.005


def v6_day(path, thru=0.02):
    """Run one qualified ticker-day. Returns list of (size, ret_pct)."""
    trades = []
    run_high = path[0]["h"]
    armed = False
    in_pos = False
    prev_bar = path[0]
    junction_depth = 0.0     # depth of the retracement currently in progress
    last_junction_depth = 0.0
    entry_px = pos_high = size = None
    n_entries = 0
    done = False
    for b in path[1:]:
        if done:
            break
        if not in_pos:
            if b["h"] > run_high:
                run_high = b["h"]
                if not armed:
                    junction_depth = 0.0
            depth = (run_high - min(b["l"], run_high)) / run_high
            junction_depth = max(junction_depth, depth)
            if junction_depth >= ABANDON:
                done = True
                break
            if depth >= ARM:
                armed = True
            if armed and n_entries < MAX_ENTRIES and b["h"] > prev_bar["h"]:
                raw = prev_bar["h"] + 0.01
                entry_px = raw * (1 + SLIP)
                size = 0.5 if last_junction_depth >= SIZE_CUT_DEPTH else 1.0
                in_pos = True
                armed = False
                n_entries += 1
                last_junction_depth = junction_depth
                pos_high = b["h"]
        else:
            pos_high = max(pos_high, b["h"])
            depth = (pos_high - min(b["l"], pos_high)) / pos_high
            if depth >= ABANDON:
                px = pos_high * (1 - ABANDON) * (1 - thru) * (1 - SLIP)
                trades.append((size, (px / entry_px - 1) * 100))
                in_pos = False
                done = True
                break
            if depth >= ARM:
                px = pos_high * (1 - ARM) * (1 - thru) * (1 - SLIP)
                trades.append((size, (px / entry_px - 1) * 100))
                in_pos = False
                # the ongoing retracement counts toward the next junction
                run_high = pos_high
                junction_depth = depth
                armed = True
        prev_bar = b
    if in_pos:
        px = path[-1]["c"] * (1 - SLIP)
        trades.append((size, (px / entry_px - 1) * 100))
    return trades


def score(scratch, thru=0.02):
    items = json.load(open(os.path.join(scratch, "res_cameron.json")))["items"]
    day_rets = {}
    all_trades = []
    for t in items:
        tr = v6_day(t["path"], thru)
        all_trades.extend(tr)
        day_rets.setdefault(t["day"], []).extend(tr)
    # per ticker-day-entry record: capital = 1 unit per trade of its size
    per_day = []
    for d, tr in day_rets.items():
        if tr:
            cap = sum(s for s, _ in tr)
            per_day.append(sum(s * r for s, r in tr) / cap if cap else 0.0)
    return all_trades, per_day, len(items), len(day_rets)


def main():
    scratches = dict(kv.split("=") for kv in os.environ["MOMO_SCRATCHES"].split(","))
    L = ["# Spec v6 results", ""]
    for name, sc in scratches.items():
        L.append(f"## {name}")
        for thru in (0.0, 0.02, 0.05):
            trades, per_day, n_items, n_days = score(sc, thru)
            r = [x for _, x in trades]
            if not r:
                L.append(f"  thru {thru:.0%}: no trades")
                continue
            w = sum(1 for x in r if x > 0)
            wd = sum(1 for x in per_day if x > 0)
            L.append(f"  thru {thru:.0%}: qual-days {n_items} | trades {len(r)} "
                     f"({len(r) / max(n_days, 1):.1f}/day) | per-trade mean "
                     f"{sum(r) / len(r):+.2f}% med {pctl(r, .5):+.2f}% WR {100 * w / len(r):.0f}% "
                     f"p10 {pctl(r, .1):+.1f}% p90 {pctl(r, .9):+.1f}%")
            L.append(f"           per-day mean {sum(per_day) / len(per_day):+.2f}% "
                     f"med {pctl(per_day, .5):+.2f}% WR {100 * wd / len(per_day):.0f}% "
                     f"p10 {pctl(per_day, .1):+.1f}% p90 {pctl(per_day, .9):+.1f}% "
                     f"worst {min(per_day):+.1f}% best {max(per_day):+.1f}%")
        L.append("")
    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(HERE, "momentum_v6_results.md"), "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()
