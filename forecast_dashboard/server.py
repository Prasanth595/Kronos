"""server.py — FastAPI backend for the custom Kronos dashboard.

This replaces the Streamlit UI with a bespoke frontend. It is still a THIN client:
all model/data logic lives in forecast_engine.py and storage.py (single source of
truth). This module only does HTTP plumbing + serialization.

Honesty framing is carried into every payload (caveats, distribution-not-point,
blind-spot). No fabricated confidence score is ever produced.

Run:
    python server.py                      # http://localhost:8000
    uvicorn server:app --host 0.0.0.0 --port 8000     # GCP
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

import forecast_engine as fe
import storage
import news_context as nc
import news_sentiment as ns
from instruments import all_instruments, get_instrument, INSTRUMENT_ORDER

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
DEVICE = os.environ.get("KRONOS_DEVICE", "cpu")

app = FastAPI(title="Kronos Forecasting Dashboard", version="1.0")

# --------------------------------------------------------------------------- #
# Activity heartbeat — touched on every API request. A separate idle-watchdog
# (deploy/watchdog.sh) reads ACTIVITY_FILE to auto-stop the GCP VM after a
# period with no traffic, so an idle demo box stops billing. Opt-in: set
# ACTIVITY_FILE on the VM; it's a no-op locally (env unset).
# --------------------------------------------------------------------------- #
ACTIVITY_FILE = os.environ.get("ACTIVITY_FILE", "").strip()


def _touch_activity() -> None:
    if not ACTIVITY_FILE:
        return
    try:
        with open(ACTIVITY_FILE, "w") as fh:
            fh.write(str(datetime.now(timezone.utc).timestamp()))
    except Exception:  # noqa: BLE001
        pass


@app.middleware("http")
async def _activity_middleware(request, call_next):
    # Health checks shouldn't count as "user activity" (the watchdog polls it),
    # so the box can still idle-stop while only being pinged.
    if ACTIVITY_FILE and not request.url.path.startswith(("/api/health", "/api/prewarm-status")):
        _touch_activity()
    return await call_next(request)


# --------------------------------------------------------------------------- #
# Predictor + simple in-process caches (forecasts are expensive)
# --------------------------------------------------------------------------- #
_predictor = None
_predictor_lock = threading.Lock()
_forecast_cache: dict = {}   # key -> result
_cache_lock = threading.Lock()
_inflight: dict = {}         # key -> threading.Lock (dedup concurrent computes)
_inflight_lock = threading.Lock()
FORECAST_TTL = 60 * 60 * 6   # 6h

# Sentiment is cheap (network + LLM) but we still cache it briefly so repeated
# views / the combined read don't re-hit the news source and LLM every request.
_sentiment_cache: dict = {}  # instrument -> (timestamp, SentimentResult)
_sentiment_lock = threading.Lock()
SENTIMENT_TTL = int(os.environ.get("SENTIMENT_TTL", "900"))  # 15 min


def _get_predictor():
    global _predictor
    if _predictor is None:
        with _predictor_lock:
            if _predictor is None:
                _predictor = fe.load_predictor(device=DEVICE)
    return _predictor


def _cache_key(instrument, lookback, pred_len, n_samples, T, top_p, timeframe):
    # Daily forecast cache is per-DAY; intraday is per (5-min) bucket so it
    # refreshes through the session without recomputing on every click.
    if timeframe == "1d":
        bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        now = datetime.now(timezone.utc)
        bucket = now.strftime("%Y-%m-%d %H:") + f"{(now.minute // 5) * 5:02d}"
    return (instrument, lookback, pred_len, n_samples, round(T, 3), round(top_p, 3),
            timeframe, bucket)


def _compute_forecast(instrument, lookback, pred_len, n_samples, T, top_p, timeframe):
    res = fe.run_forecast(
        instrument, lookback=lookback, pred_len=pred_len, n_samples=n_samples,
        T=T, top_p=top_p, device=DEVICE, predictor=_get_predictor(),
        timeframe=timeframe,
    )
    try:
        storage.log_forecast(res)
    except Exception:  # noqa: BLE001
        pass
    return res


def _get_forecast(instrument, lookback, pred_len, n_samples, T, top_p,
                  timeframe="1d", force=False):
    key = _cache_key(instrument, lookback, pred_len, n_samples, T, top_p, timeframe)
    if not force:
        with _cache_lock:
            hit = _forecast_cache.get(key)
            if hit is not None:
                return hit

    # Per-key lock so a prewarm + a visitor (or two visitors) asking for the same
    # forecast don't each run expensive CPU inference; the second waits and reuses.
    with _inflight_lock:
        lock = _inflight.setdefault(key, threading.Lock())
    with lock:
        if not force:
            with _cache_lock:
                hit = _forecast_cache.get(key)
                if hit is not None:
                    return hit
        res = _compute_forecast(instrument, lookback, pred_len, n_samples, T, top_p, timeframe)
        with _cache_lock:
            _forecast_cache[key] = res
        return res


def _get_sentiment(instrument_key: str, force: bool = False) -> ns.SentimentResult:
    """Cached news-sentiment for an instrument (Layer 2). Cheap but networked."""
    import time
    inst = get_instrument(instrument_key)
    now = time.time()
    if not force:
        with _sentiment_lock:
            hit = _sentiment_cache.get(instrument_key)
            if hit and (now - hit[0]) < SENTIMENT_TTL:
                return hit[1]
    res = ns.get_sentiment(inst.key, inst.display_name, inst.primary_ticker)
    with _sentiment_lock:
        _sentiment_cache[instrument_key] = (now, res)
    return res


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def _fmt_ts(ts, intraday: bool) -> str:
    """Daily -> 'YYYY-MM-DD'; intraday -> 'YYYY-MM-DD HH:MM' (UTC, naive)."""
    t = pd.Timestamp(ts)
    return t.strftime("%Y-%m-%d %H:%M") if intraday else str(t.date())


def _result_to_dict(res, include_samples=True, max_sample_paths=40):
    inst = get_instrument(res.instrument_key)
    hist = res.history
    skew = res.skew_metrics.reset_index()

    sample_paths = []
    if include_samples:
        n = min(res.n_samples, max_sample_paths)
        sample_paths = [[round(float(v), 6) for v in res.sample_matrix[i]] for i in range(n)]

    return {
        "instrument": res.instrument_key,
        "display_name": res.display_name,
        "ticker_used": res.ticker_used,
        "timeframe": res.timeframe,
        "timeframe_label": res.timeframe_label,
        "is_intraday": res.is_intraday,
        "used_volume_path": res.used_volume_path,
        "has_reliable_volume": res.has_reliable_volume,
        "event_sensitive": res.event_sensitive,
        "confidence_caveat": res.confidence_caveat,
        "last_close": round(res.last_close, 6),
        "last_history_date": _fmt_ts(res.last_history_date, res.is_intraday),
        "generated_at": res.generated_at.isoformat(),
        "pred_len": res.pred_len,
        "n_samples": res.n_samples,
        "realized_vol_annualized": round(res.realized_vol_annualized, 6),
        "skew_sentence": res.skew_sentence(),
        "price_lean": res.price_lean(),
        "history": {
            "dates": [_fmt_ts(d, res.is_intraday) for d in hist["timestamps"]],
            "open": [round(float(v), 6) for v in hist["open"]],
            "high": [round(float(v), 6) for v in hist["high"]],
            "low": [round(float(v), 6) for v in hist["low"]],
            "close": [round(float(v), 6) for v in hist["close"]],
        },
        "forecast": {
            "dates": [_fmt_ts(d, res.is_intraday) for d in res.future_timestamps],
            "p10": [round(float(v), 6) for v in res.p10],
            "p25": [round(float(v), 6) for v in res.p25],
            "median": [round(float(v), 6) for v in res.median],
            "p75": [round(float(v), 6) for v in res.p75],
            "p90": [round(float(v), 6) for v in res.p90],
        },
        "skew": {
            "horizon": [int(h) for h in skew["horizon"]],
            "downside": [round(float(v), 6) for v in skew["downside"]],
            "upside": [round(float(v), 6) for v in skew["upside"]],
            "prob_below_last_close": [round(float(v), 6) for v in skew["prob_below_last_close"]],
            "downside_upside_ratio": [
                (None if not np.isfinite(v) else round(float(v), 4))
                for v in skew["downside_upside_ratio"]
            ],
        },
        "sample_paths": sample_paths,
    }


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/instruments")
def api_instruments():
    return {
        "order": INSTRUMENT_ORDER,
        "instruments": [
            {
                "key": i.key,
                "display_name": i.display_name,
                "primary_ticker": i.primary_ticker,
                "has_reliable_volume": i.has_reliable_volume,
                "event_sensitive": i.event_sensitive,
                "confidence_caveat": i.confidence_caveat,
            }
            for i in all_instruments()
        ],
        "global_caveat": (
            "The model sees PAST DAILY PRICE CANDLES ONLY. It cannot see Fed/BoE/BoJ "
            "decisions, CPI, OPEC headlines, or risk events. Forecast is a distribution "
            "(a band), never a single prediction, and carries no confidence score."
        ),
    }


@app.get("/api/forecast/{instrument}")
def api_forecast(
    instrument: str,
    lookback: int = Query(400, ge=100, le=512),
    pred_len: int = Query(30, ge=5, le=60),
    n_samples: int = Query(30, ge=10, le=80),
    T: float = Query(1.0, ge=0.5, le=1.5),
    top_p: float = Query(0.9, ge=0.5, le=1.0),
    timeframe: str = Query("1d"),
    include_sentiment: bool = Query(True),
    force: bool = Query(False),
):
    try:
        get_instrument(instrument)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument '{instrument}'")
    if timeframe.lower() not in fe.TIMEFRAMES:
        raise HTTPException(status_code=400,
                            detail=f"Unknown timeframe '{timeframe}'. "
                                   f"Valid: {', '.join(fe.TIMEFRAMES)}")
    try:
        res = _get_forecast(instrument, lookback, pred_len, n_samples, T, top_p,
                            timeframe=timeframe.lower(), force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Forecast failed: {exc}")
    payload = _result_to_dict(res)
    payload["accuracy"] = storage.accuracy_summary(instrument)
    payload["analysis_text"] = nc.analyze_forecast_text(res, payload["accuracy"])

    # Layer 2 (news sentiment) + the COMBINED agree/diverge read. This is the
    # reframed headline output: two independent views shown side by side.
    if include_sentiment:
        try:
            sent = _get_sentiment(instrument, force=force)
            payload["sentiment"] = sent.to_dict()
            payload["combined"] = ns.combine(res.price_lean(), sent)
        except Exception as exc:  # noqa: BLE001 - sentiment is best-effort
            payload["sentiment"] = None
            payload["combined"] = None
            payload["sentiment_error"] = str(exc)
    return payload


@app.get("/api/glance")
def api_glance(
    lookback: int = Query(400, ge=100, le=512),
    n_samples: int = Query(30, ge=10, le=80),
):
    # Reuse the SAME 30-day daily forecast the detail view uses (shared cache key),
    # then slice the first 7 days for the 1-week summary. This avoids computing a
    # second forecast per instrument on CPU. Glance is always DAILY.
    GLANCE_PRED_LEN = 30
    SPARK_DAYS = 7
    out = []
    for inst in all_instruments():
        try:
            res = _get_forecast(inst.key, lookback, GLANCE_PRED_LEN, n_samples, 1.0, 0.9,
                                timeframe="1d", force=False)
            h = min(SPARK_DAYS, res.pred_len) - 1
            card = {
                "instrument": inst.key,
                "display_name": res.display_name,
                "ticker_used": res.ticker_used,
                "last_close": round(res.last_close, 6),
                "median_1w": round(float(res.median[h]), 6),
                "p10_1w": round(float(res.p10[h]), 6),
                "p90_1w": round(float(res.p90[h]), 6),
                "has_reliable_volume": res.has_reliable_volume,
                "event_sensitive": res.event_sensitive,
                "confidence_caveat": res.confidence_caveat,
                "price_lean": res.price_lean(),
                "forecast_dates": [str(d.date()) for d in res.future_timestamps[:SPARK_DAYS]],
                "median_series": [round(float(v), 6) for v in res.median[:SPARK_DAYS]],
                "p10_series": [round(float(v), 6) for v in res.p10[:SPARK_DAYS]],
                "p90_series": [round(float(v), 6) for v in res.p90[:SPARK_DAYS]],
            }
            # Cheap sentiment + combined verdict per card (cached).
            try:
                sent = _get_sentiment(inst.key)
                card["sentiment_score"] = round(sent.aggregate_score, 4)
                card["sentiment_label"] = sent.label
                card["sentiment_method"] = sent.method
                card["combined"] = ns.combine(res.price_lean(), sent)
            except Exception:  # noqa: BLE001
                card["sentiment_score"] = None
                card["combined"] = None
            out.append(card)
        except Exception as exc:  # noqa: BLE001
            out.append({"instrument": inst.key, "display_name": inst.display_name,
                        "error": str(exc)})
    return {"cards": out}


@app.get("/api/accuracy/{instrument}")
def api_accuracy(instrument: str):
    try:
        get_instrument(instrument)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument '{instrument}'")
    return storage.accuracy_summary(instrument)


@app.post("/api/refresh-actuals")
def api_refresh_actuals(instrument: str = Query("")):
    key = instrument.strip() or None
    if key is not None:
        try:
            get_instrument(key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown instrument '{key}'")
    n = storage.update_actuals(key)
    return {"reconciled": n, "scope": key or "all"}


@app.get("/api/news/{instrument}")
def api_news(instrument: str):
    try:
        inst = get_instrument(instrument)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument '{instrument}'")
    ctx = nc.get_news_context(inst.key, inst.display_name)
    return {
        "instrument": inst.key,
        "blind_spots": ctx.blind_spots,
        "items": [{"title": it.title, "source": it.source, "url": it.url,
                   "published": it.published} for it in ctx.items],
        "tone_note": ctx.tone_note,
        "enabled": ctx.enabled,
        "notice": ctx.notice,
        "disclaimer": nc.DISCLAIMER,
    }


@app.get("/api/sentiment/{instrument}")
def api_sentiment(instrument: str, force: bool = Query(False)):
    """Layer 2 only: live news-sentiment for an instrument (no model run)."""
    try:
        get_instrument(instrument)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown instrument '{instrument}'")
    try:
        sent = _get_sentiment(instrument, force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Sentiment failed: {exc}")
    return sent.to_dict()


@app.get("/api/timeframes")
def api_timeframes():
    """Available forecast timeframes (daily + intraday)."""
    return {
        "default": fe.DEFAULT_TIMEFRAME,
        "timeframes": [
            {"key": k, "label": v["label"], "intraday": v["intraday"]}
            for k, v in fe.TIMEFRAMES.items()
        ],
        "note": ("Intraday data is delayed ~15 min on free feeds. Sub-minute / tick "
                 "data is not available. 1m history is limited to ~7 days, 5m/15m to "
                 "~60 days, 1h to ~2 years."),
    }


@app.get("/api/health")
def api_health():
    return {"status": "ok", "device": DEVICE,
            "model": fe.DEFAULT_MODEL, "time": datetime.now(timezone.utc).isoformat()}


# --------------------------------------------------------------------------- #
# Background prewarm — so a fresh GCP boot serves instantly instead of making
# the first visitor wait ~2-3 min per instrument on CPU. Cache is per-day, so
# this runs once after startup. Disable with KRONOS_PREWARM=0.
# --------------------------------------------------------------------------- #
_prewarm_state = {"running": False, "done": [], "started_at": None}


def _prewarm_worker():
    _prewarm_state["running"] = True
    _prewarm_state["started_at"] = datetime.now(timezone.utc).isoformat()
    for inst in INSTRUMENT_ORDER:
        try:
            # detail + glance now share this one 30-day forecast (cache key match)
            _get_forecast(inst, 400, 30, 30, 1.0, 0.9, force=False)
            _prewarm_state["done"].append(inst)
        except Exception:  # noqa: BLE001
            pass
    _prewarm_state["running"] = False


@app.on_event("startup")
def _on_startup():
    if os.environ.get("KRONOS_PREWARM", "1") != "0":
        threading.Thread(target=_prewarm_worker, daemon=True).start()


@app.get("/api/prewarm-status")
def api_prewarm_status():
    return {**_prewarm_state, "instruments": INSTRUMENT_ORDER}


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port, log_level="info")
