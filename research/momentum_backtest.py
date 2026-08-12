#!/usr/bin/env python3
"""Momentum first-pullback historical backtest (spec v1).

Stage 1 (scan): full-market daily-bar sweep for morning-gap candidates.
  No-lookahead criteria: open >= 1.10 * prev_close (>=10% gain AT THE OPEN,
  which subsumes the gap-up pillar), open $2-$20, 50d avg volume computable.
  Full-day volume >= 5x avg50 is used only as a loose pre-gate: the morning
  gate below is a strict subset of it, so no candidate that would pass the
  honest gate is lost, and it saves thousands of 1-min requests.
Stage 2 (replay): pull 1-min bars per candidate day; require cumulative
  volume by 09:45 ET >= 5x avg50 (the real, no-lookahead relvol pillar),
  then run the frozen state machine from momentum_paper.replay.
Stage 3 (stats): distribution + initial-condition analysis, cost stress.

Known infidelities (accepted, reported):
- Float pillar NOT applied: FMP float is current-only; offerings/splits make
  it unreliable backwards. All backtest trades are float-unknown.
- Survivorship: universe is today's active assets; delisted pumps missing.
- Stocks that opened flat and squeezed later in the morning are not scanned
  (open-gap is the only no-lookahead daily filter available). Conservative.

Usage: python3 momentum_backtest.py [scan|replay|stats|all]
Caches under SCRATCH; delete a stage's cache file to re-run it.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

from momentum_paper import replay, minute_bars, et_hhmm, HDR, DATA

TRADE_API = "https://paper-api.alpaca.markets"
SCRATCH = os.environ.get(
    "MOMO_SCRATCH",
    "/tmp/claude-0/-home-user-Kronos/2f0190a1-7250-5bf8-81dd-e6806ae4a3ce/scratchpad/momo_bt",
)
HERE = os.path.dirname(os.path.abspath(__file__))
SCAN_START = os.environ.get("MOMO_START", "2025-08-11")
SCAN_END = os.environ.get("MOMO_END", "2026-08-08")
# ~4 extra months of runway so the 50-day volume average is warm at SCAN_START
HIST_START = (datetime.strptime(SCAN_START, "%Y-%m-%d")
              - timedelta(days=130)).strftime("%Y-%m-%d")
MAX_PER_DAY = 6
CHUNK = 200

os.makedirs(SCRATCH, exist_ok=True)


def get_retry(url, **params):
    last = None
    for k in range(8):
        try:
            r = requests.get(url, headers=HDR, params=params, timeout=120)
        except requests.exceptions.RequestException as e:  # timeouts, conn resets
            last = e
            time.sleep(3 * (k + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(4 * (k + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"retries exhausted for {url}: {last}")


def assets():
    path = os.path.join(SCRATCH, "assets.json")
    if os.path.exists(path):
        return json.load(open(path))
    js = get_retry(f"{TRADE_API}/v2/assets", status="active", asset_class="us_equity")
    bad_name = ("warrant", "unit", "right", " etf", " etn", "depositary")
    syms = []
    for a in js:
        s = a["symbol"]
        if not a.get("tradable") or a.get("exchange") == "OTC":
            continue
        if "." in s or "/" in s:
            continue
        if len(s) == 5 and s[-1] in "WRU":
            continue
        name = (a.get("name") or "").lower()
        if any(b in name for b in bad_name):
            continue
        syms.append(s)
    json.dump(syms, open(path, "w"))
    print(f"assets: {len(syms)} scannable symbols", flush=True)
    return syms


def scan():
    path = os.path.join(SCRATCH, "candidates.json")
    if os.path.exists(path):
        return json.load(open(path))
    syms = assets()
    nchunks = (len(syms) + CHUNK - 1) // CHUNK
    print(f"scanning {len(syms)} symbols {SCAN_START}..{SCAN_END}", flush=True)
    # checkpoint so a mid-scan network failure doesn't discard completed chunks
    ck_path = os.path.join(SCRATCH, "scan_partial.json")
    ck = json.load(open(ck_path)) if os.path.exists(ck_path) else {"done": [], "cands": []}
    cands = ck["cands"]
    for i in range(0, len(syms), CHUNK):
        if i in ck["done"]:
            continue
        params = dict(symbols=",".join(syms[i:i + CHUNK]), timeframe="1Day",
                      start=HIST_START, end=SCAN_END, adjustment="all",
                      feed="sip", limit=10000, sort="asc")
        allbars = {}
        while True:
            j = get_retry(f"{DATA}/v2/stocks/bars", **params)
            for s, bs in (j.get("bars") or {}).items():
                allbars.setdefault(s, []).extend(bs)
            tok = j.get("next_page_token")
            if not tok:
                break
            params["page_token"] = tok
        for s, bs in allbars.items():
            for k in range(1, len(bs)):
                d = bs[k]["t"][:10]
                if d < SCAN_START:
                    continue
                o, pc = bs[k]["o"], bs[k - 1]["c"]
                if not (2.0 <= o <= 20.0) or pc <= 0 or o < pc * 1.10:
                    continue
                hist = [b["v"] for b in bs[max(0, k - 51):k]]
                if len(hist) < 30:
                    continue
                avg50 = sum(hist[-50:]) / len(hist[-50:])
                if avg50 <= 0 or bs[k]["v"] < 5 * avg50:
                    continue  # loose pre-gate (morning gate is stricter)
                cands.append({"symbol": s, "day": d,
                              "gap_pct": round((o / pc - 1) * 100, 1),
                              "open_px": o, "prev_close": pc,
                              "avg50": round(avg50, 1)})
        ck["done"].append(i)
        ck["cands"] = cands
        json.dump(ck, open(ck_path, "w"))
        print(f"  chunk {i // CHUNK + 1}/{nchunks}: {len(cands)} raw candidates",
              flush=True)
    byday = {}
    for c in cands:
        byday.setdefault(c["day"], []).append(c)
    kept = []
    for d, lst in byday.items():
        lst.sort(key=lambda x: -x["gap_pct"])
        for r, c in enumerate(lst[:MAX_PER_DAY], 1):
            c["rank_day"] = r
            kept.append(c)
    kept.sort(key=lambda x: (x["day"], x["rank_day"]))
    json.dump(kept, open(path, "w"), indent=1)
    print(f"scan done: {len(cands)} raw, {len(kept)} kept (cap {MAX_PER_DAY}/day, "
          f"{len(byday)} days with candidates)", flush=True)
    return kept


def replays():
    path = os.path.join(SCRATCH, "results.json")
    done = json.load(open(path)) if os.path.exists(path) else {"items": []}
    seen = {(x["symbol"], x["day"]) for x in done["items"]}
    cands = scan()
    for n, c in enumerate(cands):
        if (c["symbol"], c["day"]) in seen:
            continue
        try:
            bars = minute_bars(c["symbol"], c["day"])
            cum = 0
            for b in bars:
                if et_hhmm(b["t"]) < "09:45":
                    cum += b["v"]
                else:
                    break
            det = dict(c)
            det["relvol_0945"] = round(cum / c["avg50"], 1) if c["avg50"] else 0.0
            if cum < 5 * c["avg50"]:
                item = {"symbol": c["symbol"], "day": c["day"],
                        "gate_fail": "morning_relvol", "pillars": det}
            else:
                res = replay(c["symbol"], c["day"], det, bars=bars)
                item = res if res is not None else {
                    "symbol": c["symbol"], "day": c["day"],
                    "no_pattern": True, "pillars": det}
                item["day"] = c["day"]
        except Exception as e:  # keep going; log the failure
            item = {"symbol": c["symbol"], "day": c["day"], "error": str(e)[:200]}
        done["items"].append(item)
        if (n + 1) % 50 == 0:
            json.dump(done, open(path, "w"))
            print(f"  replay {n + 1}/{len(cands)}", flush=True)
        time.sleep(0.1)
    json.dump(done, open(path, "w"))
    print(f"replay done: {len(done['items'])} items", flush=True)
    return done


def pctl(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def dist_line(name, xs):
    if not xs:
        return f"{name}: n=0"
    mean = sum(xs) / len(xs)
    return (f"{name}: n={len(xs)} mean={mean:+.2f} p25={pctl(xs, .25):+.2f} "
            f"med={pctl(xs, .5):+.2f} p75={pctl(xs, .75):+.2f} "
            f"min={min(xs):+.2f} max={max(xs):+.2f}")


def enrich(t):
    p = t.get("pillars", {})
    hh, mm = t["entry_time_et"].split(":")
    sq, sl = t["squeeze_high"], t["swing_low"]
    den = sq - sl
    return {
        "gap_pct": p.get("gap_pct"),
        "relvol_0945": p.get("relvol_0945"),
        "open_px": p.get("open_px"),
        "entry_min": int(hh) * 60 + int(mm) - 420,  # minutes after 07:00 ET
        "squeeze_pct": (sq / sl - 1) * 100 if sl else None,
        "retrace_pct": (sq - t["stop"]) / den * 100 if den > 0 else None,
        "risk_pct": (t["entry_px_raw"] - t["stop"]) / t["entry_px_raw"] * 100,
    }


def stress_r(t, s):
    e = t["entry_px_raw"] * (1 + s)
    x = t["exit_px_raw"] * (1 - s)
    den = e - t["stop"] * 0.99
    return (x - e) / den if den > 0 else None


def stats():
    done = json.load(open(os.path.join(SCRATCH, "results.json")))
    items = done["items"]
    trades = [x for x in items if x.get("exit_reason")]
    dqs = [x for x in items if x.get("no_trade")]
    gate = [x for x in items if x.get("gate_fail")]
    nopat = [x for x in items if x.get("no_pattern")]
    errs = [x for x in items if x.get("error")]

    L = []
    L.append(f"# Momentum First-Pullback Backtest v1 ({SCAN_START} -> {SCAN_END})")
    L.append("")
    L.append(f"Universe: active US equities (survivorship-biased), open-gap >=10%, "
             f"open $2-20, morning(<=09:45) volume >=5x 50d avg, top {MAX_PER_DAY} "
             f"gaps/day. Float pillar NOT applied (no historical float).")
    L.append(f"Fills: entry +0.5%, exits -0.5%, stops filled 1% through. "
             f"Spec: momentum_spec_v1.md (frozen before this backtest).")
    L.append("")
    L.append(f"Funnel: {len(items)} candidate-days -> {len(gate)} failed morning "
             f"relvol, {len(nopat)} no completed pattern, {len(dqs)} pullback DQ, "
             f"{len(errs)} data errors, {len(trades)} TRADES")
    dq_counts = {}
    for d in dqs:
        dq_counts[d["dq_reason"]] = dq_counts.get(d["dq_reason"], 0) + 1
    L.append(f"DQ breakdown: {dq_counts}")
    L.append("")

    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    rets = [t["ret_pct"] for t in trades]
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    L.append("## Distribution (after 0.5%/side slippage)")
    L.append(f"Win rate: {wins}/{len(trades)} = "
             f"{100 * wins / len(trades):.1f}%" if trades else "no trades")
    L.append(dist_line("R-multiple", rs))
    L.append(dist_line("Return % ", rets))
    if rs:
        L.append(f"Sum R = {sum(rs):+.1f} over {len(rs)} trades "
                 f"(expectancy {sum(rs) / len(rs):+.3f} R/trade)")
    L.append("")

    L.append("## Exit reasons")
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["exit_reason"], []).append(t)
    for r, ts in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        xrs = [t["r_multiple"] for t in ts if t.get("r_multiple") is not None]
        mr = sum(xrs) / len(xrs) if xrs else float("nan")
        mret = sum(t["ret_pct"] for t in ts) / len(ts)
        L.append(f"  {r:<14} n={len(ts):>4}  meanR={mr:+.2f}  mean%={mret:+.2f}")
    L.append("")

    L.append("## Cost stress (slippage per side)")
    for s in (0.0, 0.0025, 0.005, 0.01):
        srs = [v for v in (stress_r(t, s) for t in trades) if v is not None]
        if srs:
            w = sum(1 for v in srs if v > 0)
            L.append(f"  {s * 100:.2f}%/side: expectancy {sum(srs) / len(srs):+.3f} "
                     f"R/trade, sum {sum(srs):+.1f}, WR {100 * w / len(srs):.0f}%")
    L.append("")

    L.append("## Initial-condition analysis (quartiles of each metric, EXPLORATORY)")
    L.append("(multiple comparisons - treat as hypothesis-generating, not conclusions)")
    en = [(t, enrich(t)) for t in trades]
    for cond in ("gap_pct", "relvol_0945", "open_px", "entry_min",
                 "squeeze_pct", "retrace_pct", "risk_pct"):
        vals = [(e[cond], t) for t, e in en if e.get(cond) is not None]
        if len(vals) < 8:
            continue
        vals.sort(key=lambda v: v[0])
        L.append(f"### {cond}")
        qn = len(vals) // 4
        for qi in range(4):
            seg = vals[qi * qn:(qi + 1) * qn if qi < 3 else len(vals)]
            xs = [v for v, _ in seg]
            trs = [t["r_multiple"] for _, t in seg if t.get("r_multiple") is not None]
            w = sum(1 for _, t in seg if t["ret_pct"] > 0)
            mr = sum(trs) / len(trs) if trs else float("nan")
            L.append(f"  Q{qi + 1} [{min(xs):.1f}..{max(xs):.1f}]: n={len(seg)} "
                     f"WR={100 * w / len(seg):.0f}% meanR={mr:+.2f} "
                     f"medR={pctl(trs, .5):+.2f}")
    L.append("")

    L.append("## Time-half split")
    mid = (datetime.strptime(SCAN_START, "%Y-%m-%d") + (
        datetime.strptime(SCAN_END, "%Y-%m-%d")
        - datetime.strptime(SCAN_START, "%Y-%m-%d")) / 2).strftime("%Y-%m-%d")
    for label, sel in (("H1 (2025-08..2026-02)", lambda t: t["day"] < mid),
                       ("H2 (2026-02..2026-08)", lambda t: t["day"] >= mid)):
        ts = [t for t in trades if sel(t)]
        trs = [t["r_multiple"] for t in ts if t.get("r_multiple") is not None]
        if ts:
            w = sum(1 for t in ts if t["ret_pct"] > 0)
            L.append(f"  {label}: n={len(ts)} WR={100 * w / len(ts):.0f}% "
                     f"expectancy {sum(trs) / len(trs):+.3f} R/trade")
    L.append("")

    L.append("## Concentration check")
    by_sym = {}
    for t in trades:
        if t.get("r_multiple") is not None:
            by_sym.setdefault(t["symbol"], []).append(t["r_multiple"])
    sym_sum = sorted(((sum(v), k) for k, v in by_sym.items()), reverse=True)
    top5 = sym_sum[:5]
    L.append("  Top-5 symbols by summed R: "
             + ", ".join(f"{k} {v:+.1f}" for v, k in top5))
    if rs:
        excl = {k for _, k in top5}
        rest = [t["r_multiple"] for t in trades
                if t.get("r_multiple") is not None and t["symbol"] not in excl]
        if rest:
            L.append(f"  Excluding top-5 winners: expectancy "
                     f"{sum(rest) / len(rest):+.3f} R/trade over {len(rest)} trades")

    out = "\n".join(L)
    print(out)
    tag = os.environ.get("MOMO_TAG", "v1")
    with open(os.path.join(HERE, f"momentum_bt_{tag}_results.md"), "w") as f:
        f.write(out + "\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("scan", "all"):
        scan()
    if cmd in ("replay", "all"):
        replays()
    if cmd in ("stats", "all"):
        stats()


if __name__ == "__main__":
    main()
