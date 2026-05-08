"""
KRONOS EDGE Bridge v1.0 — Full Kronos skill extraction
Port 7800 | Ensemble variance confidence | Percentile path SL/TP | /recheck endpoint

Skills:
  A — Percentile path SL/TP (85th/15th pct of predicted highs/lows, 2.5×ATR hard cap)
  B — /recheck endpoint for dynamic per-bar exit decisions
  C — Ensemble variance confidence + NO_TRADE state
"""

import sys, os, time, logging, hashlib, traceback
from datetime import datetime, timezone
from threading import Lock

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

HOST               = "0.0.0.0"
PORT               = 7800
MODEL_NAME         = "NeoQuasar/Kronos-mini"
TOKENIZER_NAME     = "NeoQuasar/Kronos-Tokenizer-2k"
MAX_CONTEXT        = 400
PRED_LEN           = 5
ENSEMBLE_SIZE      = 5       # independent samples for variance
RECHECK_SAMPLES    = 1       # fast path for /recheck
TEMPERATURE        = 1.0
TOP_P              = 0.9
CACHE_TTL_SEC      = 55
MIN_BARS           = 50
ATR_PERIOD         = 14
MAX_SL_ATR_MULT    = 2.5     # hard cap on SL distance
PATH_TP_PCT        = 85      # percentile of pred_high for TP
PATH_SL_PCT        = 15      # percentile of pred_low for SL
VAR_PENALTY_THRESH = 0.6     # above this → NO_TRADE
MIN_DELTA_ATR      = 0.25    # below this → FLAT

app         = Flask(__name__)
_lock       = Lock()
_model_lock = Lock()
_cache: dict = {}
_shared_predictor = None


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


def _compute_atr(closes, highs, lows, period=ATR_PERIOD):
    n = min(len(closes), period + 1)
    if n < 2:
        return float(abs(closes[-1] - closes[-2])) if len(closes) >= 2 else 1e-8
    tr = [max(highs[-n+i] - lows[-n+i],
              abs(highs[-n+i] - closes[-n+i-1]),
              abs(lows[-n+i]  - closes[-n+i-1]))
          for i in range(1, n)]
    return float(np.mean(tr)) or 1e-8


def _run_ensemble(hist_df, x_ts, y_ts, n_samples):
    """Run n_samples independent Kronos predictions. Returns arrays of shape (n_samples, PRED_LEN)."""
    predictor = _load_model()
    feed_cols = ["open", "high", "low", "close"] + \
                [c for c in ["volume", "amount"] if c in hist_df.columns]
    x_df = hist_df[feed_cols].copy()

    pred_closes, pred_highs, pred_lows = [], [], []
    for _ in range(n_samples):
        pred_df = predictor.predict(
            df=x_df, x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=PRED_LEN, T=TEMPERATURE, top_p=TOP_P,
            sample_count=1, verbose=False,
        )
        pred_closes.append(pred_df["close"].values.copy())
        pred_highs.append(pred_df["high"].values.copy())
        pred_lows.append(pred_df["low"].values.copy())

    return np.array(pred_closes), np.array(pred_highs), np.array(pred_lows)


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

    mean_close_path = pred_closes.mean(axis=0)
    mean_high_path  = pred_highs.mean(axis=0)
    mean_low_path   = pred_lows.mean(axis=0)
    std_final       = float(pred_closes[:, -1].std())

    forecast_end = float(mean_close_path[-1])
    delta = forecast_end - current_close

    variance_penalty   = std_final / atr
    direction_strength = abs(delta) / (2.0 * atr)
    confidence = direction_strength * (1.0 - min(variance_penalty, 1.0))
    confidence = round(min(confidence, 1.0), 4)

    if variance_penalty > VAR_PENALTY_THRESH:
        signal_state = "NO_TRADE"
    elif abs(delta) < MIN_DELTA_ATR * atr:
        signal_state = "FLAT"
    elif delta > 0:
        signal_state = "BUY"
    else:
        signal_state = "SELL"

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

    sl_cap    = atr * MAX_SL_ATR_MULT
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
                "symbol":        symbol,
                "inference_ms":  round(elapsed * 1000, 1),
                "bars_used":     len(hist_df),
                "ensemble":      ENSEMBLE_SIZE,
                "model":         MODEL_NAME,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "cache_hit":     False,
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
        pc, _, _ = _run_ensemble(hist_df, x_ts, y_ts, RECHECK_SAMPLES)
        closes = hist_df["close"].values
        highs  = hist_df["high"].values
        lows   = hist_df["low"].values
        atr    = _compute_atr(closes, highs, lows)
        delta  = float(pc[0, -1]) - float(closes[-1])

        direction = "BUY"  if delta >  MIN_DELTA_ATR * atr else \
                    "SELL" if delta < -MIN_DELTA_ATR * atr else "FLAT"
        confidence = round(min(abs(delta) / (2.0 * atr), 1.0), 4)

        return jsonify({
            "symbol":        symbol,
            "direction":     direction,
            "confidence":    confidence,
            "delta":         round(delta, 5),
            "atr":           round(atr, 5),
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
    return jsonify({
        "model":          MODEL_NAME,
        "ensemble_size":  ENSEMBLE_SIZE,
        "pred_len":       PRED_LEN,
        "max_sl_atr_mult": MAX_SL_ATR_MULT,
        "path_tp_pct":    PATH_TP_PCT,
        "path_sl_pct":    PATH_SL_PCT,
        "cached_symbols": list(_cache.keys()),
    })


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
