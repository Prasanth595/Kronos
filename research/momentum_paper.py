#!/usr/bin/env python3
"""Momentum first-pullback paper trader (Sleeve E candidate).

Run after the close each weekday. Scans the day's gainers for five-pillar
candidates, replays the morning's 1-min bars through the frozen mechanical
rules in momentum_spec_v1.md, and appends any trades to momentum_paper_log.json.

Fully mechanical: no discretionary inputs, so post-close replay is honest.
Floats come from research/float_cache.json (symbol -> float shares), populated
from FMP shares-float lookups at scan time.

Usage: ALPACA_API_KEY=... ALPACA_API_SECRET=... python3 momentum_paper.py [YYYY-MM-DD]
"""
import json
import os
import sys
from datetime import datetime, timedelta

import requests

KEY = os.environ["ALPACA_API_KEY"]
SEC = os.environ["ALPACA_API_SECRET"]
HDR = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}
DATA = "https://data.alpaca.markets"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "momentum_paper_log.json")
FLOAT_CACHE_PATH = os.path.join(HERE, "float_cache.json")

SLIP = 0.005  # 0.5%/side
ENTRY_START = "07:00"
ENTRY_END = "09:45"
FLAT_TIME = "10:00"
SQUEEZE_PCT = 0.10
MAX_RETRACE = 0.50
PRICE_MIN, PRICE_MAX = 2.0, 20.0
MIN_GAIN = 10.0
MIN_RELVOL = 5.0
MAX_FLOAT = 20_000_000
MIN_GAP = 2.0


def et_offset(date_str):
    """US Eastern UTC offset (hours) for a YYYY-MM-DD date; covers 2024-2027."""
    for a, b in (("2024-03-10", "2024-11-03"), ("2025-03-09", "2025-11-02"),
                 ("2026-03-08", "2026-11-01"), ("2027-03-14", "2027-11-07")):
        if a <= date_str < b:
            return -4
    return -5


def et_hhmm(ts):
    dt = datetime.strptime(ts[:16], "%Y-%m-%dT%H:%M") + timedelta(hours=et_offset(ts[:10]))
    return dt.strftime("%H:%M")


def get(url, **params):
    r = requests.get(url, headers=HDR, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def movers(top=25):
    return get(f"{DATA}/v1beta1/screener/stocks/movers", top=top).get("gainers", [])


def daily_bars(sym, limit, end_s):
    # Alpaca defaults start to the current day when omitted, which would return
    # a single bar; always pass an explicit lookback window.
    start_s = (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%dT00:00:00Z")
    bars = get(
        f"{DATA}/v2/stocks/{sym}/bars",
        timeframe="1Day", limit=limit, adjustment="all", feed="sip",
        start=start_s, end=end_s, sort="desc",
    ).get("bars") or []
    return bars[::-1]  # chronological for callers


def minute_bars(sym, day):
    off = et_offset(day)
    want_end = f"{day}T{10 - off:02d}:16:00Z"  # 10:16 ET buffer
    cap = (datetime.utcnow() - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return get(
        f"{DATA}/v2/stocks/{sym}/bars",
        timeframe="1Min", adjustment="raw", feed="sip", limit=10000,
        start=f"{day}T{4 - off:02d}:00:00Z",  # 04:00 ET
        end=min(want_end, cap),
    ).get("bars") or []


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def check_pillars(sym, day, pct_gain, price, rank, floats, end_s):
    """Return (passes, detail dict). Uses daily bars for relvol + gap."""
    d = {"symbol": sym, "day": day, "pct_gain": round(pct_gain, 1), "price": price,
         "gainer_rank": rank}
    if not (PRICE_MIN <= price <= PRICE_MAX):
        return False, d
    if pct_gain < MIN_GAIN:
        return False, d
    bars = daily_bars(sym, 55, end_s)
    if len(bars) < 2 or bars[-1]["t"][:10] != day:
        d["reject"] = "no daily bar for scan day"
        return False, d
    today, prior = bars[-1], bars[-2]
    gap = (today["o"] / prior["c"] - 1) * 100
    d["gap_pct"] = round(gap, 1)
    hist = [b["v"] for b in bars[:-1]]
    avg_vol = sum(hist[-50:]) / len(hist[-50:])
    relvol = today["v"] / avg_vol if avg_vol else 0
    d["relvol"] = round(relvol, 1)
    d["volume"] = today["v"]
    flt = floats.get(sym)
    d["float"] = flt
    if gap < MIN_GAP:
        d["reject"] = "gap"
        return False, d
    if relvol < MIN_RELVOL:
        d["reject"] = "relvol"
        return False, d
    if flt is not None and flt >= MAX_FLOAT:
        d["reject"] = "float"
        return False, d
    d["float_unknown"] = flt is None
    d["catalyst_waived"] = rank <= 3
    return True, d


def replay(sym, day, detail, bars=None):
    """State machine per momentum_spec_v1.md. Returns trade dict or None."""
    if bars is None:
        bars = minute_bars(sym, day)
    if len(bars) < 10:
        return None
    swing_low = None
    squeeze_high = None
    squeeze_active = False
    move_green_vols = []
    pullback = []  # candles since squeeze_high
    disqualified = False
    dq_reason = None
    entered = False
    trade = None
    cum_pv = 0.0
    cum_v = 0
    ema = None
    ema_k = 2 / (9 + 1)
    prev = None
    in_window_yet = False

    for b in bars:
        t_et = et_hhmm(b["t"])
        typ = (b["h"] + b["l"] + b["c"]) / 3
        cum_pv += typ * b["v"]
        cum_v += b["v"]
        vwap = cum_pv / cum_v if cum_v else b["c"]
        ema = b["c"] if ema is None else b["c"] * ema_k + ema * (1 - ema_k)

        # VWAP/9EMA accumulate from 04:00 ET, but move detection starts at 07:00
        # ET (source watches scanners 07:00-10:00; pre-7:00 wiggles are not "the
        # first pullback").
        if t_et < ENTRY_START:
            prev = b
            continue
        if not in_window_yet:
            in_window_yet = True
            swing_low = b["l"]
        swing_low = min(swing_low, b["l"])

        if entered:
            tr = trade
            stop = tr["stop"]
            risk = tr["entry_px_raw"] - stop
            reason = None
            exit_px = None
            if b["l"] <= stop:
                reason, exit_px = "stop", stop * 0.99
            else:
                body = abs(b["c"] - b["o"])
                rng = b["h"] - b["l"]
                wick = b["h"] - max(b["c"], b["o"])
                red = b["c"] < b["o"]
                if rng > 0 and wick >= 2 * body and wick >= 0.5 * rng:
                    reason, exit_px = "topping_tail", b["c"]
                elif red and prev is not None and prev["c"] > prev["o"] and b["v"] >= 2 * prev["v"]:
                    reason, exit_px = "heavy_red", b["c"]
                elif red and body >= 0.5 * risk:
                    reason, exit_px = "material_red", b["c"]
                elif b["c"] < ema:
                    reason, exit_px = "ema_break", b["c"]
                else:
                    tr["slow_run"] = (
                        tr.get("slow_run", 0) + 1
                        if b["v"] < 0.5 * tr["entry_bar_vol"] else 0
                    )
                    if tr["slow_run"] >= 3 and b["c"] <= tr["slow_anchor"]:
                        reason, exit_px = "slowdown", b["c"]
                    if tr["slow_run"] == 1:
                        tr["slow_anchor"] = b["c"]
                if reason is None and t_et >= FLAT_TIME:
                    reason, exit_px = "time", b["o"]
            if reason:
                fill = exit_px * (1 - SLIP)
                tr["exit_time_et"] = t_et
                tr["exit_reason"] = reason
                tr["exit_px_raw"] = round(exit_px, 4)
                tr["exit_px"] = round(fill, 4)
                tr["ret_pct"] = round((fill / tr["entry_px"] - 1) * 100, 2)
                tr["r_multiple"] = round(
                    (fill - tr["entry_px"]) / (tr["entry_px"] - stop * 0.99), 2
                ) if tr["entry_px"] > stop * 0.99 else None
                tr.pop("slow_run", None)
                tr.pop("slow_anchor", None)
                return tr
            prev = b
            continue

        crossing = (
            squeeze_active and not disqualified and pullback
            and b["h"] > pullback[-1]["h"]
        )
        if crossing and len(pullback) >= 2:
            # crossing candle -> entry
            if ENTRY_START <= t_et <= ENTRY_END:
                raw = pullback[-1]["h"] + 0.01
                stop = min(c["l"] for c in pullback)
                if raw > stop:
                    trade = {
                        "symbol": sym, "date": day,
                        "entry_time_et": t_et,
                        "entry_px_raw": round(raw, 4),
                        "entry_px": round(raw * (1 + SLIP), 4),
                        "stop": round(stop, 4),
                        "squeeze_high": round(squeeze_high, 4),
                        "swing_low": round(swing_low, 4),
                        "entry_bar_vol": b["v"],
                        "pillars": detail,
                    }
                    entered = True
                    prev = b
                    continue
            else:
                disqualified, dq_reason = True, "trigger outside window"
        if squeeze_high is None or (b["h"] > squeeze_high and (not pullback or crossing)):
            # squeeze start/continuation, or resumption after a <2-candle dip
            squeeze_high = b["h"]
            pullback = []
            if b["c"] > b["o"]:
                move_green_vols.append(b["v"])
            if squeeze_high >= swing_low * (1 + SQUEEZE_PCT):
                squeeze_active = True
        elif squeeze_active and not disqualified:
            pullback.append(b)
            retrace_den = squeeze_high - swing_low
            retrace = (squeeze_high - min(c["l"] for c in pullback)) / retrace_den if retrace_den > 0 else 0
            mean_green = sum(move_green_vols) / len(move_green_vols) if move_green_vols else 0
            red = b["c"] < b["o"]
            if retrace > MAX_RETRACE:
                disqualified, dq_reason = True, "retrace>50%"
            elif red and mean_green and b["v"] > 1.25 * mean_green:
                disqualified, dq_reason = True, "heavy red vol in pullback"
            elif b["c"] < vwap:
                disqualified, dq_reason = True, "closed below VWAP"
            elif b["c"] < ema:
                disqualified, dq_reason = True, "closed below 9EMA"
        prev = b

    if entered and trade and "exit_reason" not in trade:
        last = bars[-1]
        fill = last["c"] * (1 - SLIP)
        trade["exit_time_et"] = et_hhmm(last["t"])
        trade["exit_reason"] = "data_end"
        trade["exit_px_raw"] = round(last["c"], 4)
        trade["exit_px"] = round(fill, 4)
        trade["ret_pct"] = round((fill / trade["entry_px"] - 1) * 100, 2)
        trade.pop("slow_run", None)
        trade.pop("slow_anchor", None)
        return trade
    if disqualified:
        return {"symbol": sym, "date": day, "no_trade": True, "dq_reason": dq_reason,
                "pillars": detail}
    return None


def main():
    now = datetime.utcnow()
    day = sys.argv[1] if len(sys.argv) > 1 else now.strftime("%Y-%m-%d")
    end_s = (now - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    floats = load_json(FLOAT_CACHE_PATH, {})
    log = load_json(LOG_PATH, {"spec": "momentum_spec_v1.md", "trades": [], "scans": []})

    close_gate = f"{16 - et_offset(day):02d}:16"  # 16 min past the 16:00 ET close
    if day == now.strftime("%Y-%m-%d") and now.strftime("%H:%M") < close_gate:
        print(f"{day} session incomplete (now {now.strftime('%H:%M')} UTC); "
              "run after 20:16 UTC for the full replay. Preview of live movers:")
        for rank, g in enumerate(movers(10), 1):
            print(f"  {rank:>2} {g['symbol']:<7} +{g['percent_change']:.0f}% px={g['price']}")
        return

    if any(s["day"] == day for s in log["scans"]):
        print(f"already scanned {day}; skipping (delete entry to re-run)")
        return

    gainers = movers(25)
    print(f"=== MOMENTUM SCAN {day} ({len(gainers)} gainers) ===")
    candidates = []
    for rank, g in enumerate(gainers, 1):
        ok, detail = check_pillars(g["symbol"], day, g["percent_change"], g["price"],
                                   rank, floats, end_s)
        if ok:
            candidates.append(detail)
            fu = " FLOAT?" if detail.get("float_unknown") else ""
            print(f"  CANDIDATE {detail['symbol']}: +{detail['pct_gain']}% "
                  f"relvol={detail['relvol']}x gap={detail['gap_pct']}%{fu}")

    results = []
    for det in candidates:
        res = replay(det["symbol"], day, det)
        if res is None:
            print(f"  {det['symbol']}: no valid pattern (no pullback completed / no trigger)")
        elif res.get("no_trade"):
            print(f"  {det['symbol']}: DQ - {res['dq_reason']}")
            results.append(res)
        else:
            print(f"  TRADE {res['symbol']}: in {res['entry_time_et']} @ {res['entry_px']} "
                  f"stop {res['stop']} -> out {res['exit_time_et']} @ {res['exit_px']} "
                  f"[{res['exit_reason']}] ret {res['ret_pct']}% R={res.get('r_multiple')}")
            results.append(res)

    log["scans"].append({"day": day, "n_gainers": len(gainers),
                         "n_candidates": len(candidates)})
    log["trades"].extend(results)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=1)

    real = [t for t in log["trades"] if not t.get("no_trade")]
    if real:
        rs = [t["r_multiple"] for t in real if t.get("r_multiple") is not None]
        wins = sum(1 for t in real if t["ret_pct"] > 0)
        print(f"\nRunning: {len(real)} trades, {wins} wins "
              f"({100 * wins / len(real):.0f}%), sum R = {sum(rs):+.2f}")
    else:
        print("\nRunning: no trades yet")


if __name__ == "__main__":
    main()
