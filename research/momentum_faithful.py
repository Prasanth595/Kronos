#!/usr/bin/env python3
"""Spec-faithful momentum scan + replay (per momentum_daytrading_notes.md).

Fixes three restrictions that were MY additions, not the source's:
  1. EVERY pullback is evaluated, not just the day's first. If a pullback is
     disqualified we discard it and wait for the next one, which is what the
     notes describe ("no pattern, no trade" = wait, not one-strike-out).
  2. Qualification is INTRADAY: a ticker becomes tradable the moment it is
     >=+10% vs prior close on >=5x relative volume inside 07:00-10:00 ET,
     so stocks that open flat and squeeze on news are included.
  3. No 6-per-day candidate cap.

No lookahead: the daily-bar prescan only decides which tickers to pull minute
data for (the same population a live scanner would flag). All qualification
and entry logic is re-derived bar-by-bar from the minute data, and no entry
is taken before the bar at which the ticker actually qualifies.

Exits: spec v2 dip-conditioned take-profit (momentum_spec_v2.md).

Usage: MOMO_SCRATCH=... MOMO_START=... MOMO_END=... MOMO_TAG=...
       python3 momentum_faithful.py [scan|replay|stats|all]
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

from momentum_backtest import get_retry, assets, CHUNK, SCRATCH, DATA
from momentum_paper import et_hhmm, et_offset
from momentum_v2_exits import SCHEDULE, THRESHOLDS, pctl

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("MOMO_TAG", "faithful")
SCAN_START = os.environ.get("MOMO_START", "2024-08-01")
SCAN_END = os.environ.get("MOMO_END", "2025-08-01")
HIST_START = (datetime.strptime(SCAN_START, "%Y-%m-%d")
              - timedelta(days=130)).strftime("%Y-%m-%d")

PRICE_MIN, PRICE_MAX = 2.0, 20.0
MIN_GAIN = 10.0        # % above prior close, measured intraday
MIN_RELVOL = 5.0       # cumulative volume so far vs 50d average
ENTRY_START, ENTRY_END, FLAT = "07:00", "09:45", "10:00"
SQUEEZE_PCT = 0.10
MAX_RETRACE = 0.50
SLIP = 0.005
os.makedirs(SCRATCH, exist_ok=True)


def scan():
    """Daily prescan: which tickers touched +10% intraday on heavy volume."""
    path = os.path.join(SCRATCH, "cand_faithful.json")
    if os.path.exists(path):
        return json.load(open(path))
    syms = assets()
    ck_path = os.path.join(SCRATCH, "scanf_partial.json")
    ck = json.load(open(ck_path)) if os.path.exists(ck_path) else {"done": [], "c": []}
    cands = ck["c"]
    n = (len(syms) + CHUNK - 1) // CHUNK
    for i in range(0, len(syms), CHUNK):
        if i in ck["done"]:
            continue
        params = dict(symbols=",".join(syms[i:i + CHUNK]), timeframe="1Day",
                      start=HIST_START, end=SCAN_END, adjustment="all",
                      feed="sip", limit=10000, sort="asc")
        allb = {}
        while True:
            j = get_retry(f"{DATA}/v2/stocks/bars", **params)
            for s, bs in (j.get("bars") or {}).items():
                allb.setdefault(s, []).extend(bs)
            tok = j.get("next_page_token")
            if not tok:
                break
            params["page_token"] = tok
        for s, bs in allb.items():
            for k in range(1, len(bs)):
                d = bs[k]["t"][:10]
                if d < SCAN_START:
                    continue
                b, pc = bs[k], bs[k - 1]["c"]
                if pc <= 0:
                    continue
                # touched +10% intraday, and traded in the price band
                if b["h"] < pc * 1.10:
                    continue
                if not (PRICE_MIN <= b["h"] <= PRICE_MAX * 1.5):
                    continue
                if b["l"] > PRICE_MAX or b["h"] < PRICE_MIN:
                    continue
                hist = [x["v"] for x in bs[max(0, k - 51):k]]
                if len(hist) < 30:
                    continue
                avg50 = sum(hist[-50:]) / len(hist[-50:])
                if avg50 <= 0 or b["v"] < MIN_RELVOL * avg50:
                    continue
                cands.append({"symbol": s, "day": d, "prev_close": pc,
                              "avg50": round(avg50, 1)})
        ck["done"].append(i)
        ck["c"] = cands
        json.dump(ck, open(ck_path, "w"))
        print(f"  chunk {i // CHUNK + 1}/{n}: {len(cands)} candidates", flush=True)
    json.dump(cands, open(path, "w"))
    print(f"scan done: {len(cands)} candidate-days", flush=True)
    return cands


def minute_bars(sym, day):
    off = et_offset(day)
    return get_retry(
        f"{DATA}/v2/stocks/{sym}/bars",
        timeframe="1Min", adjustment="raw", feed="sip", limit=10000,
        start=f"{day}T{4 - off:02d}:00:00Z", end=f"{day}T{16 - off:02d}:00:00Z",
    ).get("bars") or []


def replay(c, bars):
    """Return (trade|None, reason). Evaluates EVERY pullback in the window."""
    prev_close = c["prev_close"]
    cum_v = 0
    cum_pv = 0.0
    ema = None
    k = 2 / 10
    qualified = False
    leg_low = None          # low of the current up-leg
    leg_high = None         # running high of the current up-leg
    green_vols = []
    pull = []               # candles in the pullback under evaluation
    pull_dead = False       # this pullback is disqualified; wait for next leg
    n_dq = 0
    for i, b in enumerate(bars):
        t = et_hhmm(b["t"])
        cum_pv += (b["h"] + b["l"] + b["c"]) / 3 * b["v"]
        cum_v += b["v"]
        vwap = cum_pv / cum_v if cum_v else b["c"]
        ema = b["c"] if ema is None else b["c"] * k + ema * (1 - k)
        if t < ENTRY_START:
            continue
        if t >= FLAT:
            break
        # ---- qualification, re-derived live ----
        if not qualified:
            if (b["h"] >= prev_close * (1 + MIN_GAIN / 100)
                    and PRICE_MIN <= b["c"] <= PRICE_MAX
                    and cum_v >= MIN_RELVOL * c["avg50"]):
                qualified = True
                leg_low = b["l"]
                leg_high = b["h"]
                green_vols = [b["v"]]
            continue
        # ---- track legs and pullbacks ----
        # Crossing candle per the SOURCE definition: the first candle to break
        # the PRIOR candle's high, after a pullback of >= 2 completed candles
        # (a one-minute hesitation is not a pullback). Checked before the
        # new-leg-high branch so a mid-pullback crossing triggers the entry.
        if (pull and not pull_dead and len(pull) >= 2
                and b["h"] > pull[-1]["h"] and t <= ENTRY_END):
            raw = pull[-1]["h"] + 0.01
            stop = min(x["l"] for x in pull)
            if raw > stop:
                return {"symbol": c["symbol"], "day": c["day"],
                        "entry_time_et": t, "entry_px_raw": round(raw, 4),
                        "stop": round(stop, 4), "n_dq_before": n_dq,
                        "pullback_candles": len(pull),
                        "path": [{"t": et_hhmm(x["t"]), "o": x["o"], "h": x["h"],
                                  "l": x["l"], "c": x["c"]} for x in bars[i:]]}, "entry"
        if b["h"] > leg_high:
            # squeeze continues (or resumes after a <2-candle hesitation or a
            # disqualified pullback; n_dq is counted at disqualification time)
            leg_high = b["h"]
            pull = []
            pull_dead = False
            if b["c"] > b["o"]:
                green_vols.append(b["v"])
            continue
        # candle failed to make a new high -> part of a pullback
        if pull_dead:
            leg_low = min(leg_low, b["l"])
            continue
        pull.append(b)
        leg_low = min(leg_low, b["l"])
        den = leg_high - leg_low
        low_p = min(x["l"] for x in pull)
        mg = sum(green_vols) / len(green_vols) if green_vols else 0
        red = b["c"] < b["o"]
        if leg_high < leg_low * (1 + SQUEEZE_PCT) and den <= 0:
            pass
        if den > 0 and (leg_high - low_p) / den > MAX_RETRACE:
            pull_dead, n_dq = True, n_dq + 1
        elif red and mg and b["v"] > 1.25 * mg:
            pull_dead, n_dq = True, n_dq + 1
        elif b["c"] < vwap:
            pull_dead, n_dq = True, n_dq + 1
        elif b["c"] < ema:
            pull_dead, n_dq = True, n_dq + 1
        if pull_dead:
            # the failed pullback's low starts the next leg
            leg_low = low_p
    return None, ("never_qualified" if not qualified else "no_valid_pattern")


def v2_exit(tr, slip=SLIP):
    raw = tr["entry_px_raw"]
    fill = raw * (1 + slip)
    dip, tgt, out, xt = 0.0, SCHEDULE[0], None, None
    for b in tr["path"]:
        if b["t"] >= FLAT:
            out, xt = b["o"] * (1 - slip), b["t"]
            break
        dip = max(dip, (1 - b["l"] / raw) * 100)
        for th in THRESHOLDS:
            if dip >= th:
                tgt = min(tgt, SCHEDULE[th])
                break
        target = raw * (1 + tgt / 100)
        if b["h"] >= target:
            out, xt = target, b["t"]
            break
    if out is None:
        out, xt = tr["path"][-1]["c"] * (1 - slip), tr["path"][-1]["t"]
    return (out / fill - 1) * 100, xt


def replays():
    path = os.path.join(SCRATCH, os.environ.get("MOMO_RESFILE", "res_faithful.json"))
    done = json.load(open(path)) if os.path.exists(path) else {"items": [], "seen": []}
    seen = {tuple(x) for x in done["seen"]}
    cands = scan()
    for n, c in enumerate(cands):
        key = (c["symbol"], c["day"])
        if key in seen:
            continue
        try:
            tr, why = replay(c, minute_bars(c["symbol"], c["day"]))
            if tr:
                done["items"].append(tr)
        except Exception as e:
            print(f"  err {key}: {str(e)[:80]}", flush=True)
        seen.add(key)
        done["seen"].append(list(key))
        if (n + 1) % 100 == 0:
            json.dump(done, open(path, "w"))
            print(f"  replay {n + 1}/{len(cands)} -> {len(done['items'])} entries",
                  flush=True)
        time.sleep(0.03)
    json.dump(done, open(path, "w"))
    print(f"replay done: {len(done['items'])} entries", flush=True)
    return done


def stats():
    done = json.load(open(os.path.join(SCRATCH, "res_faithful.json")))
    trades = done["items"]
    days = sorted({t["day"] for t in trades})
    L = [f"# Spec-faithful momentum + v2 exits — {TAG} ({SCAN_START}..{SCAN_END})", "",
         f"Entries: {len(trades)} over {len(days)} distinct days "
         f"({len(trades) / max(len(days), 1):.1f}/trading day, "
         f"~{len(trades) / 52:.1f}/week)", ""]
    for slip in (0.005, 0.01):
        r = [v2_exit(t, slip)[0] for t in trades]
        w = [x for x in r if x > 0]
        l = [x for x in r if x <= 0]
        L.append(f"## {slip * 100:.1f}%/side")
        L.append(f"  n={len(r)} WR={100 * len(w) / len(r):.0f}% "
                 f"mean={sum(r) / len(r):+.2f}% med={pctl(r, .5):+.2f}%")
        L.append(f"  winners {len(w)} avg +{sum(w) / len(w):.1f}% | "
                 f"losers {len(l)} avg {sum(l) / len(l):.1f}% | worst {min(r):.1f}%")
        L.append("")
    r = [v2_exit(t)[0] for t in trades]
    by = {}
    for t, x in zip(trades, r):
        by.setdefault(t["symbol"], []).append(x)
    top5 = {k for _, k in sorted(((sum(v), k) for k, v in by.items()), reverse=True)[:5]}
    rest = [x for t, x in zip(trades, r) if t["symbol"] not in top5]
    L.append(f"ex-top5: n={len(rest)} mean={sum(rest) / len(rest):+.2f}%")
    mid = days[len(days) // 2]
    for lab, sel in (("H1", lambda t: t["day"] < mid), ("H2", lambda t: t["day"] >= mid)):
        seg = [x for t, x in zip(trades, r) if sel(t)]
        if seg:
            L.append(f"{lab}: n={len(seg)} mean={sum(seg) / len(seg):+.2f}%")
    nd = [t.get("n_dq_before", 0) for t in trades]
    L.append(f"\nentries taken after >=1 failed pullback: "
             f"{sum(1 for x in nd if x > 0)}/{len(nd)}")
    out = "\n".join(L)
    print(out)
    with open(os.path.join(HERE, f"momentum_faithful_{TAG}.md"), "w") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("scan", "all"):
        scan()
    if cmd in ("replay", "all"):
        replays()
    if cmd in ("stats", "all"):
        stats()
