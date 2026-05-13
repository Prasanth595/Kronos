"""
KRONOS PURE Bridge v1.0
Port 7900 | Built exclusively around Kronos model capabilities

Design principles (from Kronos Research / Alpha Trader):
  - BSQ tokenization filters micro-noise → feed M15/H1 data, not M1
  - 70% directional confluence threshold before trading
  - Ensemble via N independent predict() calls → real variance across samples
  - sample_count=1 per call (sample_count>1 averages internally, destroying variance signal)
  - Lower T=0.7 / top_p=0.7 for sharper structural direction signals
  - Full OHLCV path used: high/low for SL/TP, close for direction
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
              logging.FileHandler("kronos_pure.log", encoding="utf-8")],
)
log = logging.getLogger("KRONOS_PURE")

HOST             = "0.0.0.0"
PORT             = 7900
MODEL_PRIMARY    = "NeoQuasar/Kronos-mini"
MODEL_BACKUP     = "NeoQuasar/Kronos-base"
TOKENIZER_NAME   = "NeoQuasar/Kronos-Tokenizer-2k"
MAX_CONTEXT      = 2048         # Kronos-mini context window
MAX_CONTEXT_BK   = 512          # Kronos-base context window
PRED_LEN         = 3            # bars ahead (on M15 = 45 min, on H1 = 3h)
ENSEMBLE_SIZE    = 30           # Alpha Trader: 30 Monte Carlo paths for uncertainty view
RECHECK_SAMPLES  = 5            # recheck uses fewer for speed
TEMPERATURE      = 0.7          # lower = sharper structural direction (not random drift)
TOP_P            = 0.7          # tighter nucleus = less stochastic noise
CACHE_TTL_SEC    = 55
MIN_BARS         = 60
ATR_PERIOD       = 14
MAX_SL_ATR_MULT  = 2.5
PATH_TP_PCT      = 70           # more conservative TP — realistic for M15 horizon
PATH_SL_PCT      = 30           # tighter SL band to match
MIN_DIR_AGREE    = 0.70         # Alpha Trader threshold: 70% of samples must agree
MIN_DELTA_ATR    = 0.20

app            = Flask(__name__)
_lock          = Lock()
_model_lock    = Lock()
_cache: dict   = {}
_predictor     = None   # active predictor (primary or backup)
_active_model  = None   # tracks which model is running
_active_ctx    = None   # tracks active context window


def _get_kronos_root():
    candidates = [
        os.environ.get("KRONOS_PATH", ""),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        r"C:\Users\delac\Desktop\Kronos",
    ]
    root = next((p for p in candidates if p and os.path.isdir(os.path.join(p, "model"))), None)
    if root is None:
        raise ImportError("Kronos repo not found. Set KRONOS_PATH env var.")
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _load_model():
    """Load primary (Kronos-mini). Falls back to Kronos-base if primary fails."""
    global _predictor, _active_model, _active_ctx
    if _predictor is not None:
        return _predictor
    with _model_lock:
        if _predictor is not None:
            return _predictor
        # Try primary: Kronos-mini
        try:
            root = _get_kronos_root()
            log.info(f"Kronos repo: {root}")
            from model import Kronos, KronosTokenizer, KronosPredictor
            tok  = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
            mdl  = Kronos.from_pretrained(MODEL_PRIMARY)
            _predictor    = KronosPredictor(mdl, tok, max_context=MAX_CONTEXT)
            _active_model = MODEL_PRIMARY
            _active_ctx   = MAX_CONTEXT
            log.info(f"✅ Primary loaded: {MODEL_PRIMARY} (ctx={MAX_CONTEXT})")
            return _predictor
        except Exception as e:
            log.warning(f"⚠️ Primary failed: {e} — trying backup")
        # Fallback: Kronos-base
        try:
            root = _get_kronos_root()
            from model import Kronos, KronosTokenizer, KronosPredictor
            tok  = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
            mdl  = Kronos.from_pretrained(MODEL_BACKUP)
            _predictor    = KronosPredictor(mdl, tok, max_context=MAX_CONTEXT_BK)
            _active_model = MODEL_BACKUP
            _active_ctx   = MAX_CONTEXT_BK
            log.info(f"✅ Backup loaded: {MODEL_BACKUP} (ctx={MAX_CONTEXT_BK})")
            return _predictor
        except Exception as e:
            log.error(f"❌ Both models failed: {e}")
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
    """
    N independent predict() calls each with sample_count=1.
    sample_count>1 averages internally → destroys the variance signal we need.
    Returns arrays shape (n_samples, PRED_LEN) for close/high/low.
    """
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


def _build_signal(hist_df, pred_closes, pred_highs, pred_lows):
    """
    Kronos-native confidence = directional agreement across ensemble samples.
    Matches the 70% confluence threshold used in Alpha Trader.
    """
    closes = hist_df["close"].values
    highs  = hist_df["high"].values
    lows   = hist_df["low"].values
    current_close = float(closes[-1])
    atr = _compute_atr(closes, highs, lows)
    n   = len(pred_closes)

    # Per-sample direction at forecast horizon
    sample_deltas = pred_closes[:, -1] - current_close
    buy_votes  = int(np.sum(sample_deltas >  MIN_DELTA_ATR * atr))
    sell_votes = int(np.sum(sample_deltas < -MIN_DELTA_ATR * atr))
    flat_votes = n - buy_votes - sell_votes

    buy_agree  = buy_votes  / n
    sell_agree = sell_votes / n

    # Mean path for SL/TP
    mean_high_path = pred_highs.mean(axis=0)
    mean_low_path  = pred_lows.mean(axis=0)

    # Final close std (variance across samples)
    std_final = float(pred_closes[:, -1].std())
    variance_penalty = std_final / atr

    # Dominant direction
    # Note: variance_penalty already dampens confidence below — no hard NO_TRADE veto needed
    if buy_agree >= MIN_DIR_AGREE:
        signal_state  = "BUY"
        dir_agreement = buy_agree
    elif sell_agree >= MIN_DIR_AGREE:
        signal_state  = "SELL"
        dir_agreement = sell_agree
    else:
        signal_state  = "FLAT"
        dir_agreement = max(buy_agree, sell_agree)

    # Confidence = directional agreement dampened by variance
    confidence = round(dir_agreement * (1.0 - min(variance_penalty, 1.0)), 4)

    # Percentile path SL/TP with ATR hard cap
    sl_capped = False
    if signal_state == "BUY":
        path_tp_raw = float(np.percentile(mean_high_path, PATH_TP_PCT))
        path_sl_raw = float(np.percentile(mean_low_path,  PATH_SL_PCT))
        sl_dist = current_close - path_sl_raw
        tp_dist = path_tp_raw  - current_close
    elif signal_state == "SELL":
        path_tp_raw = float(np.percentile(mean_low_path,  100 - PATH_TP_PCT))
        path_sl_raw = float(np.percentile(mean_high_path, 100 - PATH_SL_PCT))
        sl_dist = path_sl_raw - current_close
        tp_dist = current_close - path_tp_raw
    else:
        path_tp_raw = path_sl_raw = sl_dist = tp_dist = 0.0

    # Hard cap: SL cannot exceed 2.5 × ATR
    sl_cap = atr * MAX_SL_ATR_MULT
    if sl_dist > sl_cap:
        sl_dist   = sl_cap
        sl_capped = True

    # Hard floor: SL must be at least 1.0 × ATR from entry
    # Prevents near-zero SL when model is extremely confident (all paths predict no dip)
    sl_floor = atr * 2.0
    if sl_dist < sl_floor:
        sl_dist   = sl_floor
        sl_capped = True

    if sl_capped and signal_state == "BUY":
        path_sl_raw = current_close - sl_dist
    elif sl_capped and signal_state == "SELL":
        path_sl_raw = current_close + sl_dist

    is_trade = signal_state in ("BUY", "SELL")
    reason_map = {
        "FLAT": f"no direction (B={buy_agree:.0%} S={sell_agree:.0%} var={variance_penalty:.2f})",
        "BUY":  "",
        "SELL": "",
    }

    return {
        # Primary fields (POOYER-compatible)
        "ok":                is_trade,
        "direction":         signal_state,
        "confidence":        confidence,
        "entry_ref":         round(current_close, 5),
        "path_tp":           round(path_tp_raw, 5),
        "path_sl":           round(path_sl_raw, 5),
        "reason":            reason_map.get(signal_state, ""),
        # Extended Kronos-PURE fields
        "signal_state":      signal_state,
        "dir_agreement":     round(dir_agreement, 4),
        "buy_votes":         buy_votes,
        "sell_votes":        sell_votes,
        "flat_votes":        flat_votes,
        "ensemble":          n,
        "sl_capped":         sl_capped,
        "atr":               round(atr, 5),
        "variance_penalty":  round(variance_penalty, 4),
        "std_final":         round(std_final, 5),
        "current_close":     round(current_close, 5),
        "forecast_bars":     PRED_LEN,
    }


def _bar_hash(df):
    last = df.iloc[-1]
    raw  = f"{last['open']:.5f}{last['high']:.5f}{last['low']:.5f}{last['close']:.5f}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cache(symbol, bh):
    entry = _cache.get(symbol)
    if entry and entry["hash"] == bh and time.time() - entry["ts"] < CACHE_TTL_SEC:
        return entry["result"]
    return None

def _set_cache(symbol, bh, result):
    _cache[symbol] = {"hash": bh, "result": result, "ts": time.time()}


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
        bar_freq = payload.get("freq", "15min")
        if len(bars) < MIN_BARS:
            return jsonify({"error": f"Need >={MIN_BARS} bars, got {len(bars)}"}), 400

        hist_df, x_ts, y_ts = _prepare_hist(bars, bar_freq)
        bh     = _bar_hash(hist_df)
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
            result  = _build_signal(hist_df, pc, ph, pl)
            result.update({
                "symbol":        symbol,
                "bar_freq":      bar_freq,
                "inference_ms":  round(elapsed * 1000, 1),
                "bars_used":     len(hist_df),
                "model":         _active_model or MODEL_PRIMARY,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "cache_hit":     False,
            })
            _set_cache(symbol, bh, result)
            log.info(
                f"[{symbol}/{bar_freq}] {result['signal_state']} "
                f"agree={result['dir_agreement']:.0%} "
                f"({result['buy_votes']}B/{result['sell_votes']}S/{result['flat_votes']}F) "
                f"conf={result['confidence']:.2f} var={result['variance_penalty']:.2f} "
                f"({result['inference_ms']}ms)"
            )
        return jsonify(result)
    except Exception as e:
        log.error(f"/predict error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/recheck", methods=["POST"])
def recheck():
    try:
        payload  = request.get_json(force=True) or {}
        symbol   = payload.get("symbol", "UNKNOWN").upper()
        bars     = payload.get("bars", [])
        bar_freq = payload.get("freq", "15min")
        if len(bars) < MIN_BARS:
            return jsonify({"error": f"Need >={MIN_BARS} bars"}), 400

        hist_df, x_ts, y_ts = _prepare_hist(bars, bar_freq)
        pc, _, _ = _run_ensemble(hist_df, x_ts, y_ts, RECHECK_SAMPLES)
        closes   = hist_df["close"].values
        highs    = hist_df["high"].values
        lows     = hist_df["low"].values
        atr      = _compute_atr(closes, highs, lows)

        sample_deltas = pc[:, -1] - float(closes[-1])
        n          = RECHECK_SAMPLES
        buy_votes  = int(np.sum(sample_deltas >  MIN_DELTA_ATR * atr))
        sell_votes = int(np.sum(sample_deltas < -MIN_DELTA_ATR * atr))
        buy_agree  = buy_votes  / n
        sell_agree = sell_votes / n

        if buy_agree  >= MIN_DIR_AGREE:  direction = "BUY"
        elif sell_agree >= MIN_DIR_AGREE: direction = "SELL"
        else:                             direction = "FLAT"

        confidence = round(max(buy_agree, sell_agree), 4)

        should_exit = direction == "FLAT" and confidence < MIN_DIR_AGREE * 0.5

        return jsonify({
            "ok":            direction in ("BUY", "SELL"),
            "direction":     direction,
            "confidence":    confidence,
            "should_exit":   should_exit,
            "buy_votes":     buy_votes,
            "sell_votes":    sell_votes,
            "atr":           round(atr, 5),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.error(f"/recheck error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":      "ok" if _predictor else "loading",
        "model":       _active_model or MODEL_PRIMARY,
        "model_ready": _predictor is not None,
        "port":        PORT,
        "version":     "1.0.0",
        "design":      "directional-agreement-70pct",
    })

@app.route("/warmup", methods=["POST"])
def warmup():
    try:
        _load_model()
        return jsonify({"status": "warmed_up", "model": _active_model or MODEL_PRIMARY})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stats", methods=["GET"])
def stats():
    return jsonify({
        "model":         _active_model or MODEL_PRIMARY,
        "ensemble_size": ENSEMBLE_SIZE,
        "pred_len":      PRED_LEN,
        "temperature":   TEMPERATURE,
        "top_p":         TOP_P,
        "min_dir_agree": MIN_DIR_AGREE,
        "max_sl_atr":    MAX_SL_ATR_MULT,
        "cached":        list(_cache.keys()),
    })

@app.route("/cache/clear", methods=["POST"])
def clear_cache():
    with _lock:
        _cache.clear()
    return jsonify({"status": "cleared"})


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  KRONOS PURE Bridge v1.0 — Port 7900")
    log.info("  30-path Monte Carlo | 70% confluence | T=0.7 | M15/H1 native")
    log.info("=" * 60)
    try:
        _load_model()
    except Exception as e:
        log.warning(f"Startup load failed (will retry on first request): {e}")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
