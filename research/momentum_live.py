#!/usr/bin/env python3
"""Nightly momentum runner — spec v4 (see momentum_spec_v4.md).

Scans the day's gainers, applies the five pillars with INTRADAY qualification,
replays the morning bar-by-bar for a valid pullback + crossing candle, applies
the v4 selection filter (pullback width >= 8%, price < $8.30) and the v4 exit
(no stop, arm at +4%, trail 0.75 x ATR14, flat 10:00 ET).

Logs every entry to momentum_v4_log.json, including entries that FAIL the v4
filter (flagged, excluded from headline stats) so the filter itself keeps
being measured forward.

Run after the close: ALPACA_API_KEY=... ALPACA_API_SECRET=... \
    python3 momentum_live.py [YYYY-MM-DD]
"""
import json
import os
import sys
from datetime import datetime, timedelta

from momentum_paper import (movers, daily_bars, load_json, et_hhmm, HDR, DATA,
                            FLOAT_CACHE_PATH, MAX_FLOAT, PRICE_MIN, PRICE_MAX,
                            MIN_RELVOL, get)
from momentum_faithful import replay, minute_bars

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "momentum_v4_log.json")

ARM_PCT = 4.0          # trail activates at +4% above entry
ATR_K = 0.75           # trail = 0.75 x ATR(14, 1-min) below running high
MIN_RISK_PCT = 8.0     # v4 selection: pullback width
MAX_PRICE = 8.30       # v4 selection: price ceiling
FLAT = "10:00"
SLIP = 0.005


def v4_exit(tr, slip=SLIP, thru=0.02):
    """Returns (ret_pct, exit_time, reason)."""
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    trs, prevc = [], None
    armed, hi, stop = False, None, None
    for b in tr["path"]:
        if b["t"] >= FLAT:
            return (b["o"] * (1 - slip) / fill - 1) * 100, b["t"], "time_1000"
        if stop is not None and b["l"] <= stop:
            px = stop * (1 - thru) * (1 - slip)
            return (px / fill - 1) * 100, b["t"], "atr_trail"
        if prevc is not None:
            trs.append(max(b["h"] - b["l"], abs(b["h"] - prevc), abs(b["l"] - prevc)))
        prevc = b["c"]
        if not armed:
            if b["h"] >= raw * (1 + ARM_PCT / 100):
                armed, hi = True, b["h"]
            else:
                continue
        else:
            hi = max(hi, b["h"])
        if len(trs) >= 5:
            atr = sum(trs[-14:]) / len(trs[-14:])
            cand = hi - ATR_K * atr
            stop = cand if stop is None else max(stop, cand)
    last = tr["path"][-1]
    return (last["c"] * (1 - slip) / fill - 1) * 100, last["t"], "data_end"


def main():
    now = datetime.utcnow()
    day = sys.argv[1] if len(sys.argv) > 1 else now.strftime("%Y-%m-%d")
    end_s = (now - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    floats = load_json(FLOAT_CACHE_PATH, {})
    log = load_json(LOG, {"spec": "momentum_spec_v4.md", "trades": [], "scans": []})
    if any(s["day"] == day for s in log["scans"]):
        print(f"already scanned {day}")
        return

    print(f"=== MOMENTUM v4 SCAN {day} ===")
    taken, skipped = [], []
    for rank, g in enumerate(movers(25), 1):
        sym, px = g["symbol"], g["price"]
        if not (PRICE_MIN <= px <= PRICE_MAX):
            continue
        bars = daily_bars(sym, 60, end_s)
        if len(bars) < 31 or bars[-1]["t"][:10] != day:
            continue
        prev_close = bars[-2]["c"]
        avg50 = sum(b["v"] for b in bars[-51:-1]) / len(bars[-51:-1])
        if avg50 <= 0 or bars[-1]["v"] < MIN_RELVOL * avg50:
            continue
        flt = floats.get(sym)
        if flt is not None and flt >= MAX_FLOAT:
            continue
        try:
            tr, why = replay({"symbol": sym, "day": day, "prev_close": prev_close,
                              "avg50": avg50}, minute_bars(sym, day))
        except Exception as e:
            print(f"  {sym}: error {str(e)[:60]}")
            continue
        if not tr:
            continue
        risk = (tr["entry_px_raw"] - tr["stop"]) / tr["entry_px_raw"] * 100
        ret, xt, reason = v4_exit(tr)
        rec = {"symbol": sym, "day": day, "entry_time_et": tr["entry_time_et"],
               "entry_px_raw": tr["entry_px_raw"], "pullback_low": tr["stop"],
               "risk_pct": round(risk, 2), "n_dq_before": tr.get("n_dq_before", 0),
               "float": flt, "gainer_rank": rank,
               "exit_time_et": xt, "exit_reason": reason, "ret_pct": round(ret, 2),
               "v4_qualified": bool(risk >= MIN_RISK_PCT
                                    and tr["entry_px_raw"] < MAX_PRICE)}
        (taken if rec["v4_qualified"] else skipped).append(rec)
        log["trades"].append(rec)
        tagline = "TAKE " if rec["v4_qualified"] else "skip "
        print(f"  {tagline}{sym:<6} in {tr['entry_time_et']} @ {tr['entry_px_raw']:.2f} "
              f"risk {risk:.1f}% -> out {xt} {reason} {ret:+.2f}%")

    log["scans"].append({"day": day, "taken": len(taken), "skipped": len(skipped)})
    json.dump(log, open(LOG, "w"), indent=1)

    q = [t for t in log["trades"] if t["v4_qualified"]]
    if q:
        r = [t["ret_pct"] for t in q]
        w = sum(1 for x in r if x > 0)
        print(f"\nv4 running: {len(q)} trades, {w} wins ({100 * w / len(q):.0f}%), "
              f"mean {sum(r) / len(r):+.2f}%/trade")
    else:
        print("\nv4 running: no qualified trades yet")


if __name__ == "__main__":
    main()
