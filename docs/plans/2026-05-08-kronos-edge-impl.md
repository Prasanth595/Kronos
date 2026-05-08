# KRONOS_EDGE Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `examples/kronos_edge/` — a Kronos bridge + MT5 EA that uses the full predicted OHLCV path (percentile SL/TP), ensemble variance confidence, dynamic flip-resistant exit, and forecast expiry.

**Architecture:** Python Flask bridge on port 7800 runs 5 ensemble predictions per bar, uses percentile-based path TP/SL, serves a `/recheck` endpoint for per-bar dynamic exit decisions. MT5 EA tracks flip count and bars_held per position, exits on 2 consecutive flips, confidence collapse, or forecast expiry.

**Tech Stack:** Python 3.10+, Flask, NumPy, pandas, torch, Kronos model (NeoQuasar/Kronos-mini), MQL5 (MetaTrader 5)

---

## Task 1: Scaffold the folder

**Files:**
- Create: `examples/kronos_edge/` (directory)
- Create: `examples/kronos_edge/requirements_edge.txt`

**Step 1: Create directory and requirements**

```bash
mkdir examples/kronos_edge
```

`examples/kronos_edge/requirements_edge.txt`:
```
flask>=2.3.0
numpy>=1.24.0
pandas>=2.0.0
torch>=2.0.0
```

**Step 2: Commit**

```bash
git add examples/kronos_edge/requirements_edge.txt
git commit -m "feat: scaffold kronos_edge example folder"
```

---

## Task 2: Build `kronos_edge_bridge.py` — core helpers

**Files:**
- Create: `examples/kronos_edge/kronos_edge_bridge.py`

**Step 1: Write the constants + model loader**

```python
"""
KRONOS EDGE Bridge v1.0 — Full Kronos skill extraction
Port 7800 | Ensemble variance confidence | Percentile path SL/TP | /recheck endpoint
"""

import sys, os, time, logging, hashlib, traceback
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler("kronos_edge.log", encoding="utf-8")],
)
log = logging.getLogger("KRONOS_EDGE")

HOST           = "0.0.0.0"
PORT           = 7800
MODEL_NAME     = "NeoQuasar/Kronos-mini"
TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-2k"
MAX_CONTEXT    = 400
PRED_LEN       = 5
ENSEMBLE_SIZE  = 5      # independent samples for variance
RECHECK_SAMPLES = 1     # fast path for /recheck
TEMPERATURE    = 1.0
TOP_P          = 0.9
CACHE_TTL_SEC  = 55
MIN_BARS       = 50
ATR_PERIOD     = 14
MAX_SL_ATR_MULT = 2.5   # hard cap on SL distance
PATH_TP_PCT    = 85     # percentile of pred_high for TP
PATH_SL_PCT    = 15     # percentile of pred_low for SL
VAR_PENALTY_THRESH = 0.6  # above this → NO_TRADE
MIN_DELTA_ATR  = 0.25   # below this → FLAT

app         = Flask(__name__)
_lock       = Lock()
_model_lock = Lock()
_cache: dict = {}
_shared_predictor = None
```

**Step 2: Write `_load_model()` with double-checked locking**

```python
def _load_model():
    global _shared_predictor
    if _shared_predictor is not None:
        return _shared_predictor
    with _model_lock:
        if _shared_predictor is not None:
            return _shared_predictor
        log.info(f"Loading Kronos: {MODEL_NAME}")
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if root not in sys.path:
                sys.path.insert(0, root)
            from model import Kronos, KronosTokenizer, KronosPredictor
            tok  = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
            mdl  = Kronos.from_pretrained(MODEL_NAME)
            pred = KronosPredictor(mdl, tok, max_context=MAX_CONTEXT)
            _shared_predictor = pred
            log.info("✅ Kronos loaded")
            return pred
        except Exception as e:
            log.error(f"❌ Load failed: {e}")
            raise
```

**Step 3: Write `_compute_atr()`**

```python
def _compute_atr(closes, highs, lows, period=ATR_PERIOD):
    n = min(len(closes), period + 1)
    if n < 2:
        return float(abs(closes[-1] - closes[-2])) if len(closes) >= 2 else 1e-8
    tr = [max(highs[-n+i] - lows[-n+i],
              abs(highs[-n+i] - closes[-n+i-1]),
              abs(lows[-n+i]  - closes[-n+i-1]))
          for i in range(1, n)]
    return float(np.mean(tr)) or 1e-8
```

**Step 4: Write `_run_ensemble()` — 5 independent Kronos predictions**

```python
def _run_ensemble(hist_df, x_ts, y_ts, n_samples):
    """Run n_samples independent Kronos predictions. Returns arrays of shape (n_samples, PRED_LEN)."""
    predictor = _load_model()
    feed_cols = ["open", "high", "low", "close"] + \
                [c for c in ["volume", "amount"] if c in hist_df.columns]
    x_df = hist_df[feed_cols].copy()

    pred_closes = []
    pred_highs  = []
    pred_lows   = []

    for _ in range(n_samples):
        pred_df = predictor.predict(
            df=x_df, x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=PRED_LEN, T=TEMPERATURE, top_p=TOP_P,
            sample_count=1, verbose=False,
        )
        pred_closes.append(pred_df["close"].values.copy())
        pred_highs.append(pred_df["high"].values.copy())
        pred_lows.append(pred_df["low"].values.copy())

    return (np.array(pred_closes),   # (n, PRED_LEN)
            np.array(pred_highs),
            np.array(pred_lows))
```

**Step 5: Write `_build_edge_signal()` — Skills A + C**

```python
def _build_edge_signal(hist_df, pred_closes, pred_highs, pred_lows):
    """
    Skill A: percentile path SL/TP with 2.5×ATR hard cap
    Skill C: ensemble variance confidence + NO_TRADE state
    """
    closes = hist_df["close"].values
    highs  = hist_df["high"].values
    lows   = hist_df["low"].values
    current_close = float(closes[-1])
    atr = _compute_atr(closes, highs, lows)

    # Ensemble stats
    mean_close_path = pred_closes.mean(axis=0)       # (PRED_LEN,)
    mean_high_path  = pred_highs.mean(axis=0)
    mean_low_path   = pred_lows.mean(axis=0)
    std_final       = float(pred_closes[:, -1].std()) # variance at horizon

    forecast_end = float(mean_close_path[-1])
    delta = forecast_end - current_close

    # Skill C — variance confidence
    variance_penalty    = std_final / atr
    direction_strength  = abs(delta) / (2.0 * atr)
    confidence = direction_strength * (1.0 - min(variance_penalty, 1.0))
    confidence = round(min(confidence, 1.0), 4)

    # Signal state
    if variance_penalty > VAR_PENALTY_THRESH:
        signal_state = "NO_TRADE"
    elif abs(delta) < MIN_DELTA_ATR * atr:
        signal_state = "FLAT"
    elif delta > 0:
        signal_state = "BUY"
    else:
        signal_state = "SELL"

    # Skill A — percentile path SL/TP
    if signal_state == "BUY":
        path_tp_raw = float(np.percentile(mean_high_path, PATH_TP_PCT))
        path_sl_raw = float(np.percentile(mean_low_path,  PATH_SL_PCT))
        tp_dist = path_tp_raw - current_close
        sl_dist = current_close - path_sl_raw
    elif signal_state == "SELL":
        path_tp_raw = float(np.percentile(mean_low_path,  100 - PATH_TP_PCT))
        path_sl_raw = float(np.percentile(mean_high_path, 100 - PATH_SL_PCT))
        tp_dist = current_close - path_tp_raw
        sl_dist = path_sl_raw - current_close
    else:
        tp_dist = sl_dist = 0.0
        path_tp_raw = path_sl_raw = 0.0

    # Hard cap SL
    sl_cap   = atr * MAX_SL_ATR_MULT
    sl_capped = False
    if sl_dist > sl_cap:
        sl_dist   = sl_cap
        sl_capped = True
        if signal_state == "BUY":
            path_sl_raw = current_close - sl_dist
        elif signal_state == "SELL":
            path_sl_raw = current_close + sl_dist

    return {
        "signal_state":       signal_state,
        "confidence":         confidence,
        "path_tp":            round(path_tp_raw, 5),
        "path_sl":            round(path_sl_raw, 5),
        "sl_capped":          sl_capped,
        "atr":                round(atr, 5),
        "variance_penalty":   round(variance_penalty, 4),
        "direction_strength": round(direction_strength, 4),
        "std_final":          round(std_final, 5),
        "forecast_bars":      PRED_LEN,
        "current_close":      round(current_close, 5),
        "forecast_end":       round(forecast_end, 5),
        "delta":              round(delta, 5),
    }
```

**Step 6: Write cache helpers**

```python
def _bar_hash(df):
    last = df.iloc[-1]
    raw  = f"{last['open']:.5f}{last['high']:.5f}{last['low']:.5f}{last['close']:.5f}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cache(symbol, bar_hash):
    entry = _cache.get(symbol)
    if entry and entry["hash"] == bar_hash:
        if time.time() - entry["ts"] < CACHE_TTL_SEC:
            return entry["result"]
    return None

def _set_cache(symbol, bar_hash, result):
    _cache[symbol] = {"hash": bar_hash, "result": result, "ts": time.time()}
```

**Step 7: Write `/predict` and `/recheck` endpoints**

```python
def _prepare_hist(bars, bar_freq):
    df = pd.DataFrame(bars)
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns: {required - set(df.columns)}")
    df = df[["open","high","low","close"] + [c for c in ["volume","amount"] if c in df.columns]]
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    lookback = min(len(df), MAX_CONTEXT)
    hist_df  = df.iloc[-lookback:].reset_index(drop=True)
    x_ts = pd.Series(pd.date_range(end=datetime.now(timezone.utc), periods=lookback, freq=bar_freq))
    y_ts = pd.Series(pd.date_range(start=x_ts.iloc[-1], periods=PRED_LEN+1, freq=bar_freq)[1:])
    return hist_df, x_ts, y_ts


@app.route("/predict", methods=["POST"])
def predict():
    try:
        payload  = request.get_json(force=True) or {}
        symbol   = payload.get("symbol", "UNKNOWN").upper()
        bars     = payload.get("bars", [])
        bar_freq = payload.get("freq", "1min")
        if len(bars) < MIN_BARS:
            return jsonify({"error": f"Need >={MIN_BARS} bars, got {len(bars)}"}), 400

        hist_df, x_ts, y_ts = _prepare_hist(bars, bar_freq)
        bh = _bar_hash(hist_df)
        cached = _get_cache(symbol, bh)
        if cached:
            cached["cache_hit"] = True
            return jsonify(cached)

        with _lock:
            cached = _get_cache(symbol, bh)
            if cached:
                cached["cache_hit"] = True
                return jsonify(cached)
            t0 = time.perf_counter()
            pc, ph, pl = _run_ensemble(hist_df, x_ts, y_ts, ENSEMBLE_SIZE)
            elapsed = time.perf_counter() - t0
            result = _build_edge_signal(hist_df, pc, ph, pl)
            result.update({
                "symbol":       symbol,
                "inference_ms": round(elapsed * 1000, 1),
                "bars_used":    len(hist_df),
                "ensemble":     ENSEMBLE_SIZE,
                "model":        MODEL_NAME,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "cache_hit":    False,
            })
            _set_cache(symbol, bh, result)
            log.info(f"[{symbol}] {result['signal_state']} conf={result['confidence']:.2f} "
                     f"var={result['variance_penalty']:.2f} ({result['inference_ms']}ms)")
        return jsonify(result)
    except Exception as e:
        log.error(f"/predict error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/recheck", methods=["POST"])
def recheck():
    """Skill B — lightweight per-bar re-poll for dynamic exit decisions."""
    try:
        payload  = request.get_json(force=True) or {}
        symbol   = payload.get("symbol", "UNKNOWN").upper()
        bars     = payload.get("bars", [])
        bar_freq = payload.get("freq", "1min")
        if len(bars) < MIN_BARS:
            return jsonify({"error": f"Need >={MIN_BARS} bars"}), 400

        hist_df, x_ts, y_ts = _prepare_hist(bars, bar_freq)
        # Fast path: single sample, no ensemble variance
        pc, ph, pl = _run_ensemble(hist_df, x_ts, y_ts, RECHECK_SAMPLES)
        closes = hist_df["close"].values
        highs  = hist_df["high"].values
        lows   = hist_df["low"].values
        atr    = _compute_atr(closes, highs, lows)
        delta  = float(pc[0, -1]) - float(closes[-1])
        direction = "BUY" if delta > MIN_DELTA_ATR * atr else \
                    "SELL" if delta < -MIN_DELTA_ATR * atr else "FLAT"
        confidence = round(min(abs(delta) / (2.0 * atr), 1.0), 4)

        return jsonify({
            "symbol":     symbol,
            "direction":  direction,
            "confidence": confidence,
            "delta":      round(delta, 5),
            "atr":        round(atr, 5),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.error(f"/recheck error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok" if _shared_predictor else "loading",
                    "model": MODEL_NAME, "model_ready": _shared_predictor is not None,
                    "port": PORT, "version": "1.0.0"})

@app.route("/warmup", methods=["POST"])
def warmup():
    try:
        _load_model()
        return jsonify({"status": "warmed_up", "model": MODEL_NAME})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cache/clear", methods=["POST"])
def clear_cache():
    with _lock:
        _cache.clear()
    return jsonify({"status": "cleared"})

@app.route("/stats", methods=["GET"])
def stats():
    return jsonify({"model": MODEL_NAME, "ensemble_size": ENSEMBLE_SIZE,
                    "pred_len": PRED_LEN, "max_sl_atr_mult": MAX_SL_ATR_MULT,
                    "path_tp_pct": PATH_TP_PCT, "path_sl_pct": PATH_SL_PCT,
                    "cached_symbols": list(_cache.keys())})


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  KRONOS EDGE Bridge v1.0 — Port 7800")
    log.info("  Ensemble variance | Percentile path SL/TP | Dynamic exit")
    log.info("=" * 60)
    try:
        _load_model()
    except Exception as e:
        log.warning(f"Startup load failed (will retry on first request): {e}")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
```

**Step 8: Verify logic manually**

Run the bridge (without model — just import check):
```bash
cd examples/kronos_edge
python -c "import kronos_edge_bridge; print('import OK')"
```
Expected: `import OK`

**Step 9: Commit**

```bash
git add examples/kronos_edge/kronos_edge_bridge.py
git commit -m "feat: KRONOS_EDGE bridge — ensemble variance, percentile path SL/TP, recheck endpoint"
```

---

## Task 3: Build `KRONOS_EDGE.mq5`

**Files:**
- Create: `examples/kronos_edge/KRONOS_EDGE.mq5`

**Step 1: Write header, includes, inputs**

```mql5
//+------------------------------------------------------------------+
//|                                              KRONOS_EDGE.mq5     |
//|         Full Kronos Skill EA — Ensemble Confidence + Path SL/TP  |
//|         Flip-Resistant Exit + Forecast Expiry                    |
//|         AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside(TM)        |
//+------------------------------------------------------------------+
#property copyright "AURELIA EMPIRE | ZEROEMOTIONS"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade        trade;
CPositionInfo pos;

input group "=== KRONOS EDGE BRIDGE ==="
input string  BridgeURL       = "http://127.0.0.1:7800";
input int     BarsToSend      = 400;
input int     TimeoutMS       = 10000;

input group "=== SIGNAL FILTER ==="
input double  MinConfidence   = 0.40;
input string  AllowedDir      = "BOTH";
input int     MaxPositions    = 2;

input group "=== EXIT CONDITIONS ==="
input int     FlipsToExit     = 2;          // consecutive direction flips before exit
input double  ConfCollapseRatio = 0.50;     // exit if confidence < entry_conf * this
input int     ForecastBars    = 5;          // max bars to hold (forecast expiry)

input group "=== RISK ==="
input double  RiskPercent     = 1.0;
input double  MaxSpreadPoints = 30.0;
input double  DailyLossLimit  = 3.0;
input double  FixedLots       = 0.01;

input group "=== SESSION ==="
input bool    UseKillHours    = true;
input int     KillHour1       = 10;
input int     KillHour2       = 17;
input bool    TradeMonday     = true;
input bool    TradeFriday     = false;

input group "=== MISC ==="
input int     MagicNumber     = 202601;
input string  TradeComment    = "KRONOS-EDGE";
input bool    EnableLogging   = true;
```

**Step 2: Write globals + structs**

```mql5
string   _symbol;
double   _point;
int      _digits;
double   _dailyStartBalance;
datetime _lastBarTime    = 0;
datetime _dailyResetTime = 0;
bool     _bridgeOK       = false;
int      _totalTrades    = 0;

struct KronosEdgeSignal {
   string signal_state;   // BUY / SELL / FLAT / NO_TRADE
   double confidence;
   double path_tp;
   double path_sl;
   bool   sl_capped;
   double atr;
   bool   valid;
};

struct RecheckResult {
   string direction;
   double confidence;
   bool   valid;
};

// Per-position state tracked in parallel arrays (max MaxPositions entries)
ulong    _ticket[10];
string   _entry_dir[10];
double   _entry_conf[10];
int      _bars_held[10];
int      _flip_count[10];
int      _trade_count = 0;
```

**Step 3: Write `OnInit()` and `OnDeinit()`**

```mql5
int OnInit()
{
   _symbol  = Symbol();
   _point   = Point();
   _digits  = Digits();
   _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   Log("KRONOS EDGE v1.0 | " + _symbol + " | Bridge: " + BridgeURL);
   Log("Add " + BridgeURL + " to Tools->Options->Expert Advisors->Allowed URLs");
   _bridgeOK = PingHealth();
   if(!_bridgeOK) Log("WARNING: Bridge not reachable — will retry on first bar");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Log("KRONOS EDGE deinit. Trades this session: " + IntegerToString(_totalTrades));
}
```

**Step 4: Write `OnTick()` — entry + management**

```mql5
void OnTick()
{
   datetime barTime = iTime(_symbol, PERIOD_CURRENT, 0);
   if(barTime == _lastBarTime) return;
   _lastBarTime = barTime;

   ResetDailyIfNeeded();

   // Management first — re-poll Kronos for open positions
   ManageByRecheck();

   if(!PassesSessionFilter())  { Log("Session filter: skip"); return; }
   if(!PassesDailyLossLimit()) { Log("Daily loss limit — halting"); return; }
   if(!PingHealth())           { Log("Bridge offline — skip bar"); return; }
   if(CountMyPositions() >= MaxPositions) return;

   double spread = (double)SymbolInfoInteger(_symbol, SYMBOL_SPREAD) * _point * 10;
   if(spread > MaxSpreadPoints * _point * 10) {
      Log("Spread too high — skip"); return;
   }

   KronosEdgeSignal sig;
   if(!FetchSignal(sig)) { Log("Signal fetch failed"); return; }

   Log(StringFormat("Kronos: %s conf=%.2f var_pen=%.2f path_tp=%.5f path_sl=%.5f atr=%.5f%s",
       sig.signal_state, sig.confidence, 0.0, sig.path_tp, sig.path_sl, sig.atr,
       sig.sl_capped ? " [SL CAPPED]" : ""));

   if(sig.signal_state == "NO_TRADE") { Log("NO_TRADE — variance too high"); return; }
   if(sig.signal_state == "FLAT")     { Log("FLAT — delta too small"); return; }
   if(sig.confidence < MinConfidence) {
      Log(StringFormat("Low confidence %.2f < %.2f — skip", sig.confidence, MinConfidence));
      return;
   }
   if(AllowedDir != "BOTH" && sig.signal_state != AllowedDir) {
      Log("Direction filter: skip " + sig.signal_state); return;
   }

   if(sig.signal_state == "BUY")  ExecuteTrade(ORDER_TYPE_BUY,  sig);
   if(sig.signal_state == "SELL") ExecuteTrade(ORDER_TYPE_SELL, sig);
}
```

**Step 5: Write `ManageByRecheck()` — Skill B**

```mql5
void ManageByRecheck()
{
   string bars_json = BuildBarsJSON();
   if(bars_json == "") return;

   for(int i = _trade_count - 1; i >= 0; i--)
   {
      if(!pos.SelectByTicket(_ticket[i])) {
         // Position closed externally — remove from tracking
         RemoveTradeEntry(i);
         continue;
      }
      if(pos.Magic() != MagicNumber || pos.Symbol() != _symbol) continue;

      _bars_held[i]++;

      // Forecast expiry
      if(_bars_held[i] >= ForecastBars) {
         Log(StringFormat("Ticket %d: forecast expired (%d bars) — closing",
             (int)_ticket[i], _bars_held[i]));
         trade.PositionClose(_ticket[i]);
         RemoveTradeEntry(i);
         continue;
      }

      // Re-poll Kronos
      RecheckResult rc;
      if(!FetchRecheck(bars_json, rc)) continue;

      // Flip counting
      if(rc.direction != _entry_dir[i] && rc.direction != "FLAT") {
         _flip_count[i]++;
         Log(StringFormat("Ticket %d: flip %d/%d (%s→%s)",
             (int)_ticket[i], _flip_count[i], FlipsToExit, _entry_dir[i], rc.direction));
      } else {
         _flip_count[i] = 0;
      }

      bool exit_flip  = (_flip_count[i] >= FlipsToExit);
      bool exit_conf  = (rc.confidence < _entry_conf[i] * ConfCollapseRatio);

      if(exit_flip || exit_conf) {
         string reason = exit_flip ? "consecutive flips" : "confidence collapse";
         Log(StringFormat("Ticket %d: exit — %s", (int)_ticket[i], reason));
         trade.PositionClose(_ticket[i]);
         RemoveTradeEntry(i);
      }
   }
}
```

**Step 6: Write `ExecuteTrade()`, `FetchSignal()`, `FetchRecheck()`, `BuildBarsJSON()`**

```mql5
void ExecuteTrade(ENUM_ORDER_TYPE type, const KronosEdgeSignal &sig)
{
   double ask = SymbolInfoDouble(_symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_symbol, SYMBOL_BID);
   double price = (type == ORDER_TYPE_BUY) ? ask : bid;

   double sl = NormalizeDouble(sig.path_sl, _digits);
   double tp = NormalizeDouble(sig.path_tp, _digits);
   double lots = CalcLots(MathAbs(price - sl));
   string full_comment = TradeComment + StringFormat("|c=%.2f|e=%d",
                         sig.confidence, ForecastBars);
   string comment = StringSubstr(full_comment, 0, 31);

   bool ok = (type == ORDER_TYPE_BUY)
      ? trade.Buy (lots, _symbol, price, sl, tp, comment)
      : trade.Sell(lots, _symbol, price, sl, tp, comment);

   if(ok) {
      ulong ticket = trade.ResultDeal();
      string dir   = (type == ORDER_TYPE_BUY) ? "BUY" : "SELL";
      _totalTrades++;
      RegisterTrade(ticket, dir, sig.confidence);
      Log(StringFormat("✓ %s %.2f lots @ %.5f SL=%.5f TP=%.5f conf=%.2f",
          dir, lots, price, sl, tp, sig.confidence));
   } else {
      Log("✗ Order failed: " + IntegerToString(trade.ResultRetcode())
          + " " + trade.ResultRetcodeDescription());
   }
}

bool FetchSignal(KronosEdgeSignal &sig)
{
   sig.valid = false;
   string bars_json = BuildBarsJSON();
   if(bars_json == "") return false;
   string payload = "{\"symbol\":\"" + _symbol + "\",\"bars\":" + bars_json + "}";
   char data[], result[]; string headers = "Content-Type: application/json\r\n", rh;
   StringToCharArray(payload, data, 0, StringLen(payload));
   ArrayResize(data, ArraySize(data) - 1);
   int code = WebRequest("POST", BridgeURL + "/predict", headers, TimeoutMS, data, result, rh);
   if(code != 200) { Log("HTTP " + IntegerToString(code)); return false; }
   return ParseEdgeSignal(CharArrayToString(result), sig);
}

bool FetchRecheck(const string &bars_json, RecheckResult &rc)
{
   rc.valid = false;
   string payload = "{\"symbol\":\"" + _symbol + "\",\"bars\":" + bars_json + "}";
   char data[], result[]; string headers = "Content-Type: application/json\r\n", rh;
   StringToCharArray(payload, data, 0, StringLen(payload));
   ArrayResize(data, ArraySize(data) - 1);
   int code = WebRequest("POST", BridgeURL + "/recheck", headers, 5000, data, result, rh);
   if(code != 200) return false;
   string json = CharArrayToString(result);
   rc.direction  = ExtractString(json, "direction");
   rc.confidence = ExtractDouble(json, "confidence");
   rc.valid = (rc.direction != "");
   return rc.valid;
}

string BuildBarsJSON()
{
   int bars = MathMin(BarsToSend, Bars(_symbol, PERIOD_CURRENT) - 1);
   if(bars < 50) return "";
   string j = "[";
   for(int i = bars - 1; i >= 1; i--) {
      j += StringFormat(
         "{\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%I64d}",
         iOpen(_symbol,PERIOD_CURRENT,i), iHigh(_symbol,PERIOD_CURRENT,i),
         iLow(_symbol,PERIOD_CURRENT,i),  iClose(_symbol,PERIOD_CURRENT,i),
         iVolume(_symbol,PERIOD_CURRENT,i));
      if(i > 1) j += ",";
   }
   return j + "]";
}
```

**Step 7: Write parse helpers + trade tracking + risk functions**

```mql5
bool ParseEdgeSignal(const string &json, KronosEdgeSignal &sig)
{
   sig.signal_state = ExtractString(json, "signal_state");
   sig.confidence   = ExtractDouble(json, "confidence");
   sig.path_tp      = ExtractDouble(json, "path_tp");
   sig.path_sl      = ExtractDouble(json, "path_sl");
   sig.atr          = ExtractDouble(json, "atr");
   sig.sl_capped    = (StringFind(json, "\"sl_capped\":true") >= 0);
   if(sig.signal_state == "" || sig.path_tp == 0 || sig.path_sl == 0) return false;
   if(sig.signal_state == "FLAT" || sig.signal_state == "NO_TRADE") {
      sig.valid = true; return true;
   }
   sig.valid = true;
   return true;
}

string ExtractString(const string &json, const string &key)
{
   string s = "\"" + key + "\":\"";
   int p = StringFind(json, s); if(p < 0) return "";
   p += StringLen(s);
   int e = StringFind(json, "\"", p);
   return (e < 0) ? "" : StringSubstr(json, p, e - p);
}

double ExtractDouble(const string &json, const string &key)
{
   string s = "\"" + key + "\":";
   int p = StringFind(json, s); if(p < 0) return 0.0;
   p += StringLen(s);
   string val = "";
   for(int i = p; i < p + 25; i++) {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " ") break;
      val += ch;
   }
   return StringToDouble(val);
}

void RegisterTrade(ulong ticket, string dir, double conf)
{
   if(_trade_count >= 10) return;
   _ticket[_trade_count]     = ticket;
   _entry_dir[_trade_count]  = dir;
   _entry_conf[_trade_count] = conf;
   _bars_held[_trade_count]  = 0;
   _flip_count[_trade_count] = 0;
   _trade_count++;
}

void RemoveTradeEntry(int idx)
{
   for(int i = idx; i < _trade_count - 1; i++) {
      _ticket[i]     = _ticket[i+1];
      _entry_dir[i]  = _entry_dir[i+1];
      _entry_conf[i] = _entry_conf[i+1];
      _bars_held[i]  = _bars_held[i+1];
      _flip_count[i] = _flip_count[i+1];
   }
   _trade_count--;
}

double CalcLots(double sl_dist)
{
   if(sl_dist <= 0) return FixedLots;
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amt  = balance * RiskPercent / 100.0;
   double tick_val  = SymbolInfoDouble(_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_val <= 0 || tick_size <= 0) return FixedLots;
   double lots = risk_amt / ((sl_dist / tick_size) * tick_val);
   double step = SymbolInfoDouble(_symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   lots = MathMax(SymbolInfoDouble(_symbol,SYMBOL_VOLUME_MIN),
                  MathMin(SymbolInfoDouble(_symbol,SYMBOL_VOLUME_MAX), lots));
   return NormalizeDouble(lots, 2);
}

int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--)
      if(pos.SelectByIndex(i) && pos.Magic()==MagicNumber && pos.Symbol()==_symbol) count++;
   return count;
}

bool PassesSessionFilter()
{
   if(!UseKillHours) return true;
   MqlDateTime t; TimeToStruct(TimeGMT(), t);
   if(t.hour == KillHour1 || t.hour == KillHour2) return false;
   if(!TradeMonday && t.day_of_week == 1) return false;
   if(!TradeFriday && t.day_of_week == 5) return false;
   return true;
}

bool PassesDailyLossLimit()
{
   double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
   double loss = (_dailyStartBalance - bal) / _dailyStartBalance * 100.0;
   return loss < DailyLossLimit;
}

void ResetDailyIfNeeded()
{
   MqlDateTime t; TimeToStruct(TimeGMT(), t);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00",t.year,t.mon,t.day));
   if(today > _dailyResetTime) {
      _dailyResetTime    = today;
      _dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      Log("Daily balance reset: " + DoubleToString(_dailyStartBalance, 2));
   }
}

bool PingHealth()
{
   char data[], result[]; string headers, rh;
   int code = WebRequest("GET", BridgeURL+"/health", headers, 1500, data, result, rh);
   _bridgeOK = (code == 200);
   return _bridgeOK;
}

void Log(const string &msg) { if(EnableLogging) PrintFormat("[KRONOS_EDGE] %s", msg); }
//+------------------------------------------------------------------+
```

**Step 8: Commit**

```bash
git add examples/kronos_edge/KRONOS_EDGE.mq5
git commit -m "feat: KRONOS_EDGE EA — percentile path SL/TP, flip-resistant exit, forecast expiry"
```

---

## Task 4: Write `README.md`

**Files:**
- Create: `examples/kronos_edge/README.md`

**Step 1: Write README**

````markdown
# KRONOS_EDGE — Full Kronos Skill Extraction

> Maximizes Kronos by using its predicted OHLCV path, ensemble variance, and dynamic re-polling.

## What Makes This Different from POOYER

| Feature | POOYER | KRONOS_EDGE |
|---|---|---|
| SL/TP | ATR formula | Kronos percentile path |
| Confidence | delta/ATR | Ensemble variance-adjusted |
| Exit | Fixed TP/SL only | Dynamic Kronos re-poll every bar |
| Forecast expiry | None | Auto-close after N bars |
| Signal states | BUY/SELL/FLAT | BUY/SELL/FLAT/NO_TRADE |

## Quick Start

```bash
# 1. Start bridge
cd examples/kronos_edge
pip install -r requirements_edge.txt
python kronos_edge_bridge.py
# Bridge on http://127.0.0.1:7800

# 2. MT5 setup
# - Copy KRONOS_EDGE.mq5 to Experts/
# - Compile (F7)
# - Add http://127.0.0.1:7800 to Allowed URLs
# - Attach to chart
```

## Bridge Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /predict` | Full signal: state, confidence, path_tp, path_sl |
| `POST /recheck` | Lightweight: current direction + confidence (for exit decisions) |
| `GET /health` | Model status |
| `GET /stats` | Runtime config |
| `POST /warmup` | Pre-load model |
| `POST /cache/clear` | Clear bar cache |

## Signal States

| State | Meaning |
|---|---|
| `BUY` | Kronos forecasts upward move, variance acceptable |
| `SELL` | Kronos forecasts downward move, variance acceptable |
| `FLAT` | Forecast delta < 0.25 × ATR — move too small to trade |
| `NO_TRADE` | Ensemble variance too high — model is uncertain |

## EA Exit Logic

The EA closes a position when **any** of these trigger:
1. **2 consecutive direction flips** — Kronos disagrees on 2 back-to-back bars
2. **Confidence collapse** — confidence drops below `entry_confidence × 0.5`
3. **Forecast expiry** — position held for `ForecastBars` bars (default: 5)

## Tuning (after live observation)

- `MinConfidence` — increase if too many losing trades, decrease if too few trades
- `FlipsToExit` — tighten to 1 for faster exits, loosen to 3 for more patience
- `ForecastBars` — match to your chart timeframe's expected move duration
- `VAR_PENALTY_THRESH` (bridge) — lower to reduce NO_TRADE frequency

## Credits
- **Kronos** — Yu Shi et al., AAAI 2026 ([arXiv:2508.02739](https://arxiv.org/abs/2508.02739))
- **KRONOS_EDGE** — Contributed by [janpauldelacruz](https://github.com/janpauldelacruz)
````

**Step 2: Commit**

```bash
git add examples/kronos_edge/README.md
git commit -m "docs: KRONOS_EDGE README — endpoints, signal states, exit logic, tuning guide"
```

---

## Task 5: Push and verify on GitHub

**Step 1: Push to fork**

```bash
git push myfork feature/mt5-bridge
```

**Step 2: Verify on GitHub**

Check `https://github.com/janpauldelacruz/Kronos/tree/feature/mt5-bridge/examples/kronos_edge` shows all 4 files.

**Step 3: Final commit check**

```bash
git log --oneline -5
```

Expected: 5 clean commits on `feature/mt5-bridge`.
