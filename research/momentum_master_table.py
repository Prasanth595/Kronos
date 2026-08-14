#!/usr/bin/env python3
"""Master table of ALL Cameron-faithful base entries. No performance filtering.

One row per entry produced by the faithful scanner (momentum_faithful.py) over
both historical windows. Descriptive columns + boolean flags for every
after-the-fact filter, so subsets are always visible next to the base.

Output: momentum_master_table.csv + a per-group summary.

Usage: MOMO_OOS=... MOMO_IS=... python3 momentum_master_table.py
"""
import csv
import json
import os

from momentum_live import v5_exit
from momentum_v2_exits import pctl

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = {"OOS_2024_25": os.environ["MOMO_OOS"], "IS_2025_26": os.environ["MOMO_IS"]}
FLOATS = json.load(open(os.path.join(HERE, "float_cache.json"))) \
    if os.path.exists(os.path.join(HERE, "float_cache.json")) else {}


def rows():
    out = []
    for win, sc in WINDOWS.items():
        cands = {(c["symbol"], c["day"]): c
                 for c in json.load(open(os.path.join(sc, "cand_faithful.json")))}
        for t in json.load(open(os.path.join(sc, "res_faithful.json")))["items"]:
            c = cands.get((t["symbol"], t["day"]))
            if c is None:
                continue
            e = t["entry_px_raw"]
            path = t["path"]
            pre10 = [b for b in path if b["t"] < "10:00"] or path[:1]
            at10 = next((b["o"] for b in path if b["t"] >= "10:00"), path[-1]["c"])
            mfe10 = (max(b["h"] for b in pre10) / e - 1) * 100
            mae10 = (min(b["l"] for b in pre10) / e - 1) * 100
            mfe_d = (max(b["h"] for b in path) / e - 1) * 100
            mae_d = (min(b["l"] for b in path) / e - 1) * 100
            hh, mm = t["entry_time_et"].split(":")
            width = (e - t["stop"]) / e * 100
            ret_v5, _, v5_reason = v5_exit(t)
            r = {
                "window": win, "day": t["day"], "symbol": t["symbol"],
                "entry_time_et": t["entry_time_et"],
                "entry_min_after_7": int(hh) * 60 + int(mm) - 420,
                "entry_px": round(e, 4),
                "prev_close": c["prev_close"],
                "gain_at_entry_pct": round((e / c["prev_close"] - 1) * 100, 1),
                "avg50_vol": c["avg50"],
                "float_shares": FLOATS.get(t["symbol"], ""),
                "pullback_low": t["stop"],
                "pullback_width_pct": round(width, 2),
                "n_rejected_pullbacks_before": t.get("n_dq_before", 0),
                "mfe_by_10_pct": round(mfe10, 1),
                "mae_by_10_pct": round(mae10, 1),
                "ret_at_10_pct": round((at10 / e - 1) * 100, 1),
                "mfe_day_pct": round(mfe_d, 1),
                "mae_day_pct": round(mae_d, 1),
                "ret_close_pct": round((path[-1]["c"] / e - 1) * 100, 1),
                "hit_p5": int(mfe_d >= 5), "hit_p10": int(mfe_d >= 10),
                "hit_p20": int(mfe_d >= 20), "hit_p50": int(mfe_d >= 50),
                "ret_v5exit_pct": round(ret_v5, 2),
                "v5_exit_reason": v5_reason,
                # ---- flags: filters are COLUMNS, never row-removal ----
                "first_pullback": int(t.get("n_dq_before", 0) == 0),
                "price_lt_8_30": int(e < 8.3),
                "pullback_width_ge_8": int(width >= 8),
                "v5_qualified": int(e < 8.3 and width >= 8),
            }
            out.append(r)
    out.sort(key=lambda r: (r["day"], r["symbol"]))
    return out


def summarize(rs, label):
    if not rs:
        return f"  {label:<26} n=0"
    n = len(rs)
    v5r = [r["ret_v5exit_pct"] for r in rs]
    w = sum(1 for x in v5r if x > 0)
    return (f"  {label:<26}{n:>5}{n / 104:>7.1f}"
            f"{pctl([r['mfe_by_10_pct'] for r in rs], .5):>+8.1f}"
            f"{pctl([r['mae_by_10_pct'] for r in rs], .5):>+8.1f}"
            f"{100 * sum(r['hit_p10'] for r in rs) / n:>6.0f}%"
            f"{100 * sum(r['hit_p20'] for r in rs) / n:>6.0f}%"
            f"{sum(v5r) / n:>+9.2f}{pctl(v5r, .5):>+8.1f}{100 * w / n:>5.0f}%")


def main():
    rs = rows()
    path = os.path.join(HERE, "momentum_master_table.csv")
    with open(path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=list(rs[0].keys()))
        wtr.writeheader()
        wtr.writerows(rs)
    print(f"wrote {path}: {len(rs)} base entries "
          f"({sum(1 for r in rs if r['window'].startswith('OOS'))} OOS, "
          f"{sum(1 for r in rs if r['window'].startswith('IS'))} IS)\n")
    hdr = (f"  {'group':<26}{'n':>5}{'/wk':>7}{'medMFE10':>8}{'medMAE10':>8}"
           f"{'hit10':>7}{'hit20':>7}{'v5exMean':>9}{'v5exMed':>8}{'WR':>6}")
    print(hdr)
    print(summarize(rs, "ALL base entries"))
    print(summarize([r for r in rs if r["first_pullback"]], "first pullback"))
    print(summarize([r for r in rs if r["price_lt_8_30"]], "price < 8.30"))
    print(summarize([r for r in rs if r["pullback_width_ge_8"]], "width >= 8%"))
    print(summarize([r for r in rs if r["v5_qualified"]], "v5 subset"))
    print(summarize([r for r in rs if not r["v5_qualified"]], "NOT v5 (the skipped)"))
    for win in ("OOS_2024_25", "IS_2025_26"):
        print(summarize([r for r in rs if r["window"] == win], win))


if __name__ == "__main__":
    main()
