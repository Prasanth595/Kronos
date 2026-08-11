#!/usr/bin/env python3
"""Raw post-entry movement analysis for momentum first-pullback entries.

For every entered trade in the backtest, measures pure price movement from the
raw entry price (no slippage, no exit mechanics): max favorable / adverse
excursion and checkpoints at 10:00 ET and the 16:00 ET close, plus which came
first, k*R or the pullback low (touch-based, R = entry - stop).

Entry-bar note: the entry occurs intrabar; the entry bar's full high/low are
included in excursions (partially pre-entry - unavoidable at 1-min data).
Ties (kR and stop touched in the same bar) count as stop-first (conservative).
"""
import json
import os

from momentum_paper import et_hhmm, et_offset, get, DATA

SCRATCH = os.environ.get(
    "MOMO_SCRATCH",
    "/tmp/claude-0/-home-user-Kronos/2f0190a1-7250-5bf8-81dd-e6806ae4a3ce/scratchpad/momo_bt",
)
HERE = os.path.dirname(os.path.abspath(__file__))


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


def dline(name, xs):
    m = sum(xs) / len(xs)
    return (f"{name:<22} mean={m:+7.2f}  p25={pctl(xs, .25):+7.2f}  "
            f"med={pctl(xs, .5):+7.2f}  p75={pctl(xs, .75):+7.2f}  "
            f"min={min(xs):+7.2f}  max={max(xs):+8.2f}")


def main():
    done = json.load(open(os.path.join(SCRATCH, "results.json")))
    trades = [x for x in done["items"] if x.get("exit_reason")]
    rows = []
    for t in trades:
        bars = day_bars(t["symbol"], t["day"])
        idx = next((i for i, b in enumerate(bars)
                    if et_hhmm(b["t"]) == t["entry_time_et"]), None)
        if idx is None:
            continue
        e, stop = t["entry_px_raw"], t["stop"]
        risk = e - stop
        post = bars[idx:]
        w10 = [b for b in post if et_hhmm(b["t"]) < "10:00"]
        row = {"symbol": t["symbol"], "day": t["day"]}
        if w10:
            row["mfe10"] = (max(b["h"] for b in w10) / e - 1) * 100
            row["mae10"] = (min(b["l"] for b in w10) / e - 1) * 100
            row["at10"] = (w10[-1]["c"] / e - 1) * 100
        row["mfeD"] = (max(b["h"] for b in post) / e - 1) * 100
        row["maeD"] = (min(b["l"] for b in post) / e - 1) * 100
        row["close"] = (post[-1]["c"] / e - 1) * 100
        first = {}
        for k in (1, 2, 3):
            first[k] = None
            tgt = e + k * risk
            for b in post:
                hit_t = b["h"] >= tgt
                hit_s = b["l"] <= stop
                if hit_s:  # ties conservative
                    first[k] = "stop"
                    break
                if hit_t:
                    first[k] = "target"
                    break
        row["race"] = first
        rows.append(row)

    n = len(rows)
    print(f"Post-entry movement, {n} entries (raw prices, no slippage, "
          f"no exit rules)\n")
    print("Within the 7:00-10:00 window (% from entry):")
    print(dline("  max favorable (MFE)", [r["mfe10"] for r in rows if "mfe10" in r]))
    print(dline("  max adverse   (MAE)", [r["mae10"] for r in rows if "mae10" in r]))
    print(dline("  price at 10:00", [r["at10"] for r in rows if "at10" in r]))
    print("\nFull day, entry -> 16:00 close (% from entry):")
    print(dline("  max favorable (MFE)", [r["mfeD"] for r in rows]))
    print(dline("  max adverse   (MAE)", [r["maeD"] for r in rows]))
    print(dline("  close vs entry", [r["close"] for r in rows]))

    print("\nShare of entries whose day-MFE reached at least:")
    for th in (2, 5, 10, 20, 50):
        c = sum(1 for r in rows if r["mfeD"] >= th)
        print(f"  +{th:>2}%: {c}/{n} = {100 * c / n:.0f}%")
    print("Share of entries whose day-MAE went at least as low as:")
    for th in (-2, -5, -10, -20):
        c = sum(1 for r in rows if r["maeD"] <= th)
        print(f"  {th:>3}%: {c}/{n} = {100 * c / n:.0f}%")

    print("\nRace vs the pullback low (touch-based, R = entry - stop):")
    for k in (1, 2, 3):
        tg = sum(1 for r in rows if r["race"][k] == "target")
        st = sum(1 for r in rows if r["race"][k] == "stop")
        nei = n - tg - st
        print(f"  +{k}R first: {tg}/{n} = {100 * tg / n:.0f}%   "
              f"stop first: {st}/{n} = {100 * st / n:.0f}%   "
              f"neither touched: {nei}")

    json.dump(rows, open(os.path.join(SCRATCH, "movement.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
