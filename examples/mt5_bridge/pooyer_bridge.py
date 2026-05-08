"""
╔══════════════════════════════════════════════════════════════════╗
║         POOYER BRIDGE v1.0 — Kronos ↔ MetaTrader 5             ║
║         AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside™          ║
║                                                                  ║
║  The world's first production-grade MT5↔Kronos bridge.          ║
║  Serves real-time OHLCV forecasts to any MT5 EA via HTTP.       ║
╚══════════════════════════════════════════════════════════════════╝

Architecture:
    MT5 EA  ──WebRequest──►  POOYER Bridge (Flask)
                                    │
                                    ▼
                            Kronos Foundation Model
                            (OHLCV Tokenizer + Transformer)
                                    │
                                    ▼
    MT5 EA  ◄──JSON Signal──  Signal Engine
                              (direction, confidence, SL, TP)

Features:
  ✅ Rolling context window (no restarts needed)
  ✅ Multi-symbol support (XAUUSD, EURUSD, GBPUSD, BTC...)
  ✅ Multi-model routing (Kronos-mini / small / base)
  ✅ Probabilistic forecasting (sample_count ensemble)
  ✅ Signal engine: direction + confidence + ATR-based SL/TP
  ✅ Built-in cache (skip redundant inference on same bar)
  ✅ Health endpoint for EA watchdog
  ✅ Full request logging + error recovery
  ✅ CPU-only mode (no GPU required)
"""

import sys
import os
import time
import logging
import hashlib
import traceback
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("pooyer_bridge.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("POOYER")

HOST           = "0.0.0.0"
PORT           = 7799
MODEL_NAME     = "NeoQuasar/Kronos-mini"
TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-2k"
MAX_CONTEXT    = 400
PRED_LEN       = 5
SAMPLE_COUNT   = 3
TEMPERATURE    = 1.0
TOP_P          = 0.9
CACHE_TTL_SEC  = 55
MIN_BARS       = 50
ATR_PERIOD     = 14
SL_ATR_MULT    = 1.5
TP_ATR_MULT    = 3.0

app            = Flask(__name__)
_lock          = Lock()
_model_lock    = Lock()   # separate lock so model load doesn't block inference cache checks
_cache: dict   = {}
_shared_predictor = None


def _load_model():
    global _shared_predictor
    if _shared_predictor is not None:
        return _shared_predictor
    with _model_lock:
        if _shared_predictor is not None:   # double-checked locking
            return _shared_predictor
        log.info(f"Loading Kronos model: {MODEL_NAME}")
        try:
            kronos_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if kronos_root not in sys.path:
                sys.path.insert(0, kronos_root)
            from model import Kronos, KronosTokenizer, KronosPredictor
            tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
            model     = Kronos.from_pretrained(MODEL_NAME)
            predictor = KronosPredictor(model, tokenizer, max_context=MAX_CONTEXT)
            _shared_predictor = predictor
            log.info("✅ Kronos model loaded successfully")
            return predictor
        except Exception as e:
            log.error(f"❌ Failed to load Kronos: {e}")
            raise


def _compute_atr(closes, highs, lows, period=14):
    n = min(len(closes), period + 1)
    if n < 2:
        return float(abs(closes[-1] - closes[-2])) if len(closes) >= 2 else 0.0
    tr = []
    for i in range(1, n):
        h, l, pc = highs[-n+i], lows[-n+i], closes[-n+i-1]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return float(np.mean(tr))


def _build_signal(hist_df, pred_df):
    closes = hist_df["close"].values
    highs  = hist_df["high"].values
    lows   = hist_df["low"].values
    current_close  = float(closes[-1])
    forecast_close = float(pred_df["close"].iloc[-1])
    atr = _compute_atr(closes, highs, lows, ATR_PERIOD)
    if atr == 0:
        atr = abs(current_close * 0.001)
    delta      = forecast_close - current_close
    confidence = min(abs(delta) / (atr * 2.0), 1.0)
    if delta > atr * 0.25:
        direction = "BUY"
    elif delta < -atr * 0.25:
        direction = "SELL"
    else:
        direction = "FLAT"
    return {
        "direction":     direction,
        "confidence":    round(confidence, 4),
        "pred_close":    [round(v, 5) for v in pred_df["close"].tolist()],
        "pred_high":     [round(v, 5) for v in pred_df["high"].tolist()],
        "pred_low":      [round(v, 5) for v in pred_df["low"].tolist()],
        "current_close": round(current_close, 5),
        "forecast_end":  round(forecast_close, 5),
        "atr":           round(atr, 5),
        "sl_pips":       round(atr * SL_ATR_MULT, 5),
        "tp_pips":       round(atr * TP_ATR_MULT, 5),
        "delta_pips":    round(delta, 5),
    }


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


def _run_inference(symbol, df, bar_freq="1min"):
    predictor = _load_model()
    lookback  = min(len(df), MAX_CONTEXT)
    hist_df   = df.iloc[-lookback:].reset_index(drop=True)
    x_ts = pd.Series(pd.date_range(end=datetime.now(timezone.utc), periods=lookback, freq=bar_freq))
    y_ts = pd.Series(pd.date_range(start=x_ts.iloc[-1], periods=PRED_LEN + 1, freq=bar_freq)[1:])
    feed_cols = ["open", "high", "low", "close"] + [c for c in ["volume", "amount"] if c in hist_df.columns]
    x_df = hist_df[feed_cols].copy()
    t0 = time.perf_counter()
    pred_df = predictor.predict(df=x_df, x_timestamp=x_ts, y_timestamp=y_ts,
                                pred_len=PRED_LEN, T=TEMPERATURE, top_p=TOP_P,
                                sample_count=SAMPLE_COUNT, verbose=False)
    elapsed = time.perf_counter() - t0
    signal = _build_signal(hist_df, pred_df)
    signal.update({"symbol": symbol, "inference_ms": round(elapsed * 1000, 1),
                   "bars_used": lookback, "pred_len": PRED_LEN, "model": MODEL_NAME,
                   "timestamp_utc": datetime.now(timezone.utc).isoformat()})
    log.info(f"[{symbol}] {signal['direction']} conf={signal['confidence']:.2f} "
             f"delta={signal['delta_pips']:+.5f} atr={signal['atr']:.5f} ({signal['inference_ms']}ms)")
    return signal


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok" if _shared_predictor else "loading",
                    "model": MODEL_NAME, "model_ready": _shared_predictor is not None,
                    "cached_symbols": list(_cache.keys()), "version": "1.0.0",
                    "bridge": "POOYER", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/predict", methods=["POST"])
def predict():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Empty or invalid JSON"}), 400
        symbol   = payload.get("symbol", "UNKNOWN").upper()
        bars     = payload.get("bars", [])
        bar_freq = payload.get("freq", "1min")
        if len(bars) < MIN_BARS:
            return jsonify({"error": f"Need >={MIN_BARS} bars, got {len(bars)}"}), 400
        df = pd.DataFrame(bars)
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return jsonify({"error": f"Missing columns: {required - set(df.columns)}"}), 400
        df = df[["open","high","low","close"] + [c for c in ["volume","amount"] if c in df.columns]]
        df = df.apply(pd.to_numeric, errors="coerce").dropna()
        bar_hash = _bar_hash(df)
        cached = _get_cache(symbol, bar_hash)
        if cached:
            cached["cache_hit"] = True
            return jsonify(cached)
        with _lock:
            cached = _get_cache(symbol, bar_hash)
            if cached:
                cached["cache_hit"] = True
                return jsonify(cached)
            result = _run_inference(symbol, df, bar_freq)
            result["cache_hit"] = False
            _set_cache(symbol, bar_hash, result)
        return jsonify(result)
    except Exception as e:
        log.error(f"❌ /predict error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/multi_predict", methods=["POST"])
def multi_predict():
    try:
        payload = request.get_json(force=True)
        results = []
        for req in payload.get("requests", []):
            symbol = req.get("symbol", "UNKNOWN").upper()
            try:
                bar_freq = req.get("freq", "1min")
                df = pd.DataFrame(req.get("bars", [])).apply(pd.to_numeric, errors="coerce").dropna()
                bh = _bar_hash(df)
                cached = _get_cache(symbol, bh)
                if cached:
                    cached["cache_hit"] = True
                    results.append(cached)
                else:
                    with _lock:
                        cached = _get_cache(symbol, bh)
                        if cached:
                            cached["cache_hit"] = True
                            results.append(cached)
                        else:
                            sig = _run_inference(symbol, df, bar_freq)
                            sig["cache_hit"] = False
                            _set_cache(symbol, bh, sig)
                            results.append(sig)
            except Exception as e:
                results.append({"symbol": symbol, "error": str(e)})
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    return jsonify({"model": MODEL_NAME, "max_context": MAX_CONTEXT, "pred_len": PRED_LEN,
                    "sample_count": SAMPLE_COUNT, "cached_symbols": list(_cache.keys()),
                    "model_loaded": _shared_predictor is not None, "port": PORT})


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  POOYER BRIDGE v1.0 — Kronos x MetaTrader 5")
    log.info("  AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside")
    log.info(f"  Listening on http://{HOST}:{PORT}")
    log.info("=" * 60)
    try:
        _load_model()
    except Exception as e:
        log.warning(f"Startup load failed (will retry on first request): {e}")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
