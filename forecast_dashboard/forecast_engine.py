"""forecast_engine.py — THE CORE. Single source of truth for all model + data logic.

Every client (Streamlit app, MCP server, notebook) imports from here. No model or
data logic is duplicated anywhere else.

Honesty principles baked into the engine (see SCOPE.md §0):
  - Forecast is a DISTRIBUTION of independent sample paths, never a single point.
  - We expose p10..p90 bands + the full sample matrix so clients can show the fan.
  - We carry the per-instrument confidence caveat through to every result.
  - The model sees price candles ONLY. It cannot see news / macro events.

Run the smoke test:  python forecast_engine.py
"""

from __future__ import annotations

import os
import sys
import math
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from instruments import Instrument, get_instrument, all_instruments

# --------------------------------------------------------------------------- #
# Kronos repo discovery. This dashboard ships *inside* the Kronos repo (at
# Kronos/forecast_dashboard/), so by default the model package lives in the
# parent directory. We still honour an explicit KRONOS_DIR override and fall
# back to a sibling ./Kronos clone, so the engine also works if this folder is
# copied out and used standalone.
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)  # Kronos repo root when shipped inside it


def _discover_kronos_dir() -> str:
    # 1) explicit override
    env = os.environ.get("KRONOS_DIR")
    if env:
        return env
    # 2) shipped inside the Kronos repo: model package is in the parent dir
    if os.path.isdir(os.path.join(_PARENT, "model")):
        return _PARENT
    # 3) standalone: a sibling ./Kronos clone next to this folder
    return os.path.join(_HERE, "Kronos")


KRONOS_DIR = _discover_kronos_dir()
if KRONOS_DIR and KRONOS_DIR not in sys.path and os.path.isdir(KRONOS_DIR):
    sys.path.insert(0, KRONOS_DIR)


# --------------------------------------------------------------------------- #
# Defaults (overridable via .env / function args)
# --------------------------------------------------------------------------- #
DEFAULT_MODEL = os.environ.get("KRONOS_MODEL", "NeoQuasar/Kronos-small")
DEFAULT_TOKENIZER = os.environ.get("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base")
DEFAULT_DEVICE = os.environ.get("KRONOS_DEVICE", "cpu")
MAX_CONTEXT = 512  # hard cap for Kronos-small/base
TRADING_DAYS_PER_YEAR = 252

# --------------------------------------------------------------------------- #
# Timeframes — daily + intraday. Kronos treats minute candles the same way it
# treats daily candles (it just reads OHLCV tokens), so the ONLY things that
# change per timeframe are: the yfinance interval, how far back free data goes,
# how we step future timestamps, and the volatility annualization factor.
#
# yfinance free-data limits (hard caps we respect):
#   1m  -> last 7 days     5m/15m -> last 60 days     1h -> last 730 days
# Sub-minute / tick data is NOT available on free feeds, so we stop at 1m.
# --------------------------------------------------------------------------- #
TIMEFRAMES: dict[str, dict] = {
    "1d":  {"interval": "1d",  "period": None, "freq": None,
            "label": "Daily", "intraday": False, "periods_per_year": 252,
            "horizon_unit": "d"},
    "1h":  {"interval": "60m", "period": "729d", "freq": "60min",
            "label": "1 hour", "intraday": True, "periods_per_year": 24 * 252,
            "horizon_unit": "h"},
    "15m": {"interval": "15m", "period": "59d", "freq": "15min",
            "label": "15 min", "intraday": True, "periods_per_year": 96 * 252,
            "horizon_unit": "bar"},
    "5m":  {"interval": "5m",  "period": "59d", "freq": "5min",
            "label": "5 min", "intraday": True, "periods_per_year": 288 * 252,
            "horizon_unit": "bar"},
    "1m":  {"interval": "1m",  "period": "7d", "freq": "1min",
            "label": "1 min", "intraday": True, "periods_per_year": 1440 * 252,
            "horizon_unit": "bar"},
}
DEFAULT_TIMEFRAME = "1d"


def timeframe_config(timeframe: str) -> dict:
    tf = (timeframe or DEFAULT_TIMEFRAME).lower()
    if tf not in TIMEFRAMES:
        raise KeyError(f"Unknown timeframe '{timeframe}'. "
                       f"Valid: {', '.join(TIMEFRAMES)}")
    return TIMEFRAMES[tf]


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #
@dataclass
class ForecastResult:
    """Everything a client needs to honestly render a forecast distribution."""

    instrument_key: str
    display_name: str
    ticker_used: str
    used_volume_path: bool          # True if OHLC-only (no-volume) path was used
    has_reliable_volume: bool
    confidence_caveat: str
    event_sensitive: bool

    last_close: float
    last_history_date: pd.Timestamp
    generated_at: datetime

    # Forecast horizon
    pred_len: int
    n_samples: int
    future_timestamps: pd.DatetimeIndex

    # Per-horizon percentile arrays (length == pred_len)
    p10: np.ndarray
    p25: np.ndarray
    median: np.ndarray            # p50
    p75: np.ndarray
    p90: np.ndarray

    # Full close-price sample matrix (n_samples x pred_len) for the fan plot
    sample_matrix: np.ndarray

    # Recent history kept for plotting context (DataFrame: timestamps, ohlcv)
    history: pd.DataFrame

    # Risk metrics
    realized_vol_annualized: float   # from recent daily log returns (HISTORICAL)
    skew_metrics: pd.DataFrame       # per-horizon skew + downside probability

    # Sampling params used (for logging / reproducibility framing)
    T: float = 1.0
    top_p: float = 0.9
    model_name: str = DEFAULT_MODEL

    # Timeframe metadata (daily vs intraday)
    timeframe: str = DEFAULT_TIMEFRAME
    timeframe_label: str = "Daily"
    is_intraday: bool = False

    def price_lean(self, horizon: Optional[int] = None) -> str:
        """Directional lean of the median vs last close at a horizon.

        Used by the combined (price + news) read. Returns 'higher' | 'lower' |
        'flat'. 'flat' when the median move is within a small fraction of price
        (noise), so we don't over-read tiny drifts.
        """
        if horizon is None:
            horizon = min(4, self.pred_len - 1)
        horizon = max(0, min(horizon, self.pred_len - 1))
        med = float(self.median[horizon])
        if self.last_close == 0:
            return "flat"
        move = (med - self.last_close) / self.last_close
        # 0.25% threshold for daily; scale down for intraday noise.
        thresh = 0.0025 if not self.is_intraday else 0.0008
        if move > thresh:
            return "higher"
        if move < -thresh:
            return "lower"
        return "flat"

    def horizon_table(self) -> pd.DataFrame:
        """Daily Low/Median/High forecast-distribution table for display."""
        return pd.DataFrame(
            {
                "date": self.future_timestamps,
                "Low (p10)": self.p10,
                "p25": self.p25,
                "Median (p50)": self.median,
                "p75": self.p75,
                "High (p90)": self.p90,
            }
        )

    def summary_text(self) -> str:
        """Plain-text summary with honesty framing — reused by the MCP server."""
        lines = []
        lines.append(f"{self.display_name}  (ticker used: {self.ticker_used})")
        lines.append(f"Last close: {self.last_close:,.4f}  as of {self.last_history_date.date()}")
        lines.append(
            f"Forecast: DISTRIBUTION of {self.n_samples} independent sample paths over "
            f"{self.pred_len} business days (NOT a single prediction)."
        )
        lines.append("")
        lines.append("Per-horizon band (Low p10 / Median p50 / High p90):")
        # Show a few representative horizons
        idxs = sorted(set([0,
                           min(4, self.pred_len - 1),
                           min(9, self.pred_len - 1),
                           self.pred_len - 1]))
        for i in idxs:
            d = self.future_timestamps[i].date()
            lines.append(
                f"  +{i+1:>2}d {d}:  {self.p10[i]:,.4f}  |  {self.median[i]:,.4f}  |  {self.p90[i]:,.4f}"
            )
        lines.append("")
        # Skew interpretation
        lines.append(self.skew_sentence())
        lines.append(f"Historical realized volatility (annualized): {self.realized_vol_annualized*100:,.1f}%")
        lines.append("")
        if self.used_volume_path is False and not self.has_reliable_volume:
            lines.append("[!] No-volume forecast path was used (volume data unreliable).")
        lines.append(f"CAVEAT: {self.confidence_caveat}")
        lines.append("CAVEAT: The model sees PAST PRICE CANDLES ONLY. It does not see Fed/BoE/BoJ "
                     "decisions, CPI, OPEC headlines, or any news/risk events.")
        return "\n".join(lines)

    def skew_sentence(self) -> str:
        """One plain-English sentence interpreting the downside/upside skew."""
        # Use a ~2-week horizon if available, else the last horizon
        h = min(9, self.pred_len - 1)
        row = self.skew_metrics.iloc[h]
        ratio = row["downside_upside_ratio"]
        below = row["prob_below_last_close"] * 100
        day = h + 1
        if not math.isfinite(ratio) or ratio <= 0:
            return (f"At the +{day}-day horizon, ~{below:.0f}% of sample paths are below the current price.")
        if ratio >= 1.15:
            shape = f"the downside tail is ~{ratio:.1f}x the upside"
        elif ratio <= 0.87:
            shape = f"the upside tail is ~{1/ratio:.1f}x the downside"
        else:
            shape = "the tails are roughly symmetric"
        return (f"At the +{day}-day horizon, {shape}; "
                f"~{below:.0f}% of sample paths end below the current price.")

    def to_log_dict(self) -> dict:
        """Compact dict for storage.py logging (one row per forecast run)."""
        return {
            "instrument_key": self.instrument_key,
            "ticker_used": self.ticker_used,
            "model_name": self.model_name,
            "generated_at": self.generated_at.isoformat(),
            "last_history_date": self.last_history_date.isoformat(),
            "last_close": float(self.last_close),
            "pred_len": int(self.pred_len),
            "n_samples": int(self.n_samples),
            "used_volume_path": bool(self.used_volume_path),
            "T": float(self.T),
            "top_p": float(self.top_p),
            "future_timestamps": [ts.isoformat() for ts in self.future_timestamps],
            "p10": [float(v) for v in self.p10],
            "p25": [float(v) for v in self.p25],
            "median": [float(v) for v in self.median],
            "p75": [float(v) for v in self.p75],
            "p90": [float(v) for v in self.p90],
        }


# --------------------------------------------------------------------------- #
# Predictor loading (expensive — cache and reuse)
# --------------------------------------------------------------------------- #
_PREDICTOR_CACHE: dict = {}
_PREDICTOR_LOCK = threading.Lock()


def load_predictor(model_name: str = DEFAULT_MODEL,
                   tokenizer_name: str = DEFAULT_TOKENIZER,
                   device: str = DEFAULT_DEVICE,
                   max_context: int = MAX_CONTEXT):
    """Load tokenizer + model + KronosPredictor once and reuse.

    Loading downloads weights from HuggingFace on first run (~100MB cached locally)
    and is slow, so we cache by (model, tokenizer, device, max_context).

    `device` is passed explicitly to KronosPredictor (do NOT rely on its default).
    """
    key = (model_name, tokenizer_name, device, max_context)
    if key in _PREDICTOR_CACHE:
        return _PREDICTOR_CACHE[key]
    with _PREDICTOR_LOCK:
        if key in _PREDICTOR_CACHE:
            return _PREDICTOR_CACHE[key]
        try:
            from model import Kronos, KronosTokenizer, KronosPredictor
        except ImportError as exc:
            raise ImportError(
                "Could not import Kronos. Clone it and set KRONOS_DIR, e.g.\n"
                "  git clone https://github.com/shiyu-coder/Kronos.git\n"
                f"Expected repo root on sys.path. KRONOS_DIR={KRONOS_DIR!r}"
            ) from exc

        tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
        model = Kronos.from_pretrained(model_name)
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=max_context)
        _PREDICTOR_CACHE[key] = predictor
        return predictor


# --------------------------------------------------------------------------- #
# Data fetching
# --------------------------------------------------------------------------- #
def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance returns multi-index (tuple) columns — flatten + lowercase them."""
    df = df.copy()
    df.columns = [
        (c[0].lower() if isinstance(c, tuple) else str(c).lower()) for c in df.columns
    ]
    return df


def _volume_is_reliable(volume: pd.Series) -> bool:
    """Heuristic: volume is junk if it's empty, all-zero, or all-NaN."""
    if volume is None or len(volume) == 0:
        return False
    v = pd.to_numeric(volume, errors="coerce").fillna(0.0)
    if (v <= 0).all():
        return False
    # If the vast majority of rows are zero, treat as unreliable.
    nonzero_frac = float((v > 0).mean())
    return nonzero_frac >= 0.30


def _download(ticker: str, lookback_days: int, timeframe: str = DEFAULT_TIMEFRAME) -> pd.DataFrame:
    """Download OHLCV via yfinance and return a clean flat DataFrame.

    For daily we request a day window; for intraday we use the per-timeframe
    `period` cap (yfinance refuses longer windows for fine intervals).
    """
    import yfinance as yf

    tf = timeframe_config(timeframe)
    interval = tf["interval"]
    if tf["intraday"]:
        period = tf["period"]
        raw = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=False, progress=False, threads=False,
        )
    else:
        period_days = max(lookback_days + 60, 120)
        raw = yf.download(
            ticker, period=f"{period_days}d", interval=interval,
            auto_adjust=False, progress=False, threads=False,
        )
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    raw = _flatten_columns(raw)
    raw = raw.reset_index()
    # The datetime column may be 'date' or 'datetime' after flattening/reset.
    ts_col = None
    for cand in ("date", "datetime", "index"):
        if cand in raw.columns:
            ts_col = cand
            break
    if ts_col is None:
        ts_col = raw.columns[0]
    raw = raw.rename(columns={ts_col: "timestamps"})
    keep = ["timestamps", "open", "high", "low", "close", "volume"]
    have = [c for c in keep if c in raw.columns]
    raw = raw[have].copy()
    # Intraday timestamps are tz-aware (UTC/exchange); drop tz to keep one code path.
    ts = pd.to_datetime(raw["timestamps"])
    try:
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        else:
            ts = ts.dt.tz_localize(None)
    except (TypeError, AttributeError):
        ts = ts.dt.tz_localize(None)
    raw["timestamps"] = ts
    for c in ("open", "high", "low", "close", "volume"):
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return raw


def fetch_ohlcv(instrument_key: str, lookback_days: int = 900,
                timeframe: str = DEFAULT_TIMEFRAME) -> pd.DataFrame:
    """Fetch OHLCV for an instrument with primary -> fallback ticker logic.

    Returns a clean DataFrame with columns:
        timestamps, open, high, low, close, volume, amount
    plus attributes on `df.attrs`:
        ticker_used (str), volume_is_reliable (bool)

    The `amount` column is SYNTHETIC (volume * close); Yahoo does not provide it.
    """
    inst = get_instrument(instrument_key)
    candidates = [inst.primary_ticker]
    if inst.fallback_ticker:
        candidates.append(inst.fallback_ticker)

    df = pd.DataFrame()
    ticker_used = inst.primary_ticker
    for ticker in candidates:
        attempt = _download(ticker, lookback_days, timeframe=timeframe)
        if len(attempt) >= 50:  # need enough rows to be useful
            df = attempt
            ticker_used = ticker
            # If this instrument is supposed to have reliable volume but the primary
            # returned junk volume, try the fallback before giving up.
            if inst.has_reliable_volume and not _volume_is_reliable(df.get("volume")) \
                    and ticker == inst.primary_ticker and inst.fallback_ticker:
                continue
            break

    if len(df) == 0:
        raise RuntimeError(
            f"No usable data for {inst.display_name} "
            f"(tried tickers: {', '.join(candidates)})."
        )

    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)

    volume_reliable = inst.has_reliable_volume and _volume_is_reliable(df["volume"])
    # Synthetic 'amount' column (documented as volume*close).
    df["amount"] = df["volume"] * df["close"]

    df = df[["timestamps", "open", "high", "low", "close", "volume", "amount"]].copy()
    df.attrs["ticker_used"] = ticker_used
    df.attrs["volume_is_reliable"] = bool(volume_reliable)
    df.attrs["instrument_key"] = instrument_key
    return df


# --------------------------------------------------------------------------- #
# Skew / downside-tail metrics
# --------------------------------------------------------------------------- #
def compute_skew_metrics(sample_matrix: np.ndarray, last_close: float) -> pd.DataFrame:
    """Per-horizon skew + downside probability from the close-price sample matrix.

    Args:
        sample_matrix: shape (n_samples, pred_len) of forecast close prices.
        last_close:    most recent actual close.

    Returns a DataFrame indexed by horizon (1..pred_len) with columns:
        median, p10, p90,
        downside (median - p10), upside (p90 - median),
        downside_upside_ratio  (downside / upside; >1 means fatter left tail),
        prob_below_last_close   (fraction of samples below current price).
    """
    sm = np.asarray(sample_matrix, dtype=float)
    if sm.ndim != 2:
        raise ValueError("sample_matrix must be 2-D (n_samples x pred_len)")
    pred_len = sm.shape[1]

    median = np.median(sm, axis=0)
    p10 = np.percentile(sm, 10, axis=0)
    p90 = np.percentile(sm, 90, axis=0)
    downside = median - p10
    upside = p90 - median
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(upside > 0, downside / upside, np.nan)
    prob_below = (sm < last_close).mean(axis=0)

    return pd.DataFrame(
        {
            "horizon": np.arange(1, pred_len + 1),
            "median": median,
            "p10": p10,
            "p90": p90,
            "downside": downside,
            "upside": upside,
            "downside_upside_ratio": ratio,
            "prob_below_last_close": prob_below,
        }
    ).set_index("horizon")


def realized_volatility(close: pd.Series, window: int = 30,
                         periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized realized volatility from recent log returns (HISTORICAL).

    `periods_per_year` lets intraday timeframes annualize correctly (e.g. hourly
    bars use 24*252). The number is still HISTORICAL realized vol, distinct from
    the forecast band width.
    """
    c = pd.to_numeric(close, errors="coerce").dropna()
    if len(c) < 5:
        return float("nan")
    log_ret = np.log(c / c.shift(1)).dropna()
    recent = log_ret.tail(window)
    if len(recent) < 2:
        return float("nan")
    return float(recent.std(ddof=1) * math.sqrt(periods_per_year))


# --------------------------------------------------------------------------- #
# Future timestamps — business days for daily, fixed-frequency bars for intraday
# --------------------------------------------------------------------------- #
def _future_business_days(last_date: pd.Timestamp, pred_len: int) -> pd.DatetimeIndex:
    """pred_len business days strictly after last_date."""
    start = pd.Timestamp(last_date).normalize() + pd.offsets.BDay(1)
    return pd.bdate_range(start=start, periods=pred_len)


def _future_timestamps(last_date: pd.Timestamp, pred_len: int,
                       timeframe: str = DEFAULT_TIMEFRAME) -> pd.DatetimeIndex:
    """Future timestamps after last_date, stepping by the timeframe.

    Daily uses business days. Intraday steps by the bar frequency (e.g. 60min);
    these are naive continuation stamps for display/logging — markets have gaps,
    but Kronos itself only consumes the candle sequence, not wall-clock spacing.
    """
    tf = timeframe_config(timeframe)
    if not tf["intraday"]:
        return _future_business_days(last_date, pred_len)
    freq = tf["freq"]
    start = pd.Timestamp(last_date) + pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(start=start, periods=pred_len, freq=freq)


# --------------------------------------------------------------------------- #
# The main forecast call
# --------------------------------------------------------------------------- #
def run_forecast(instrument_key: str,
                 lookback: int = 400,
                 pred_len: int = 30,
                 n_samples: int = 30,
                 T: float = 1.0,
                 top_p: float = 0.9,
                 top_k: int = 0,
                 device: str = DEFAULT_DEVICE,
                 model_name: str = DEFAULT_MODEL,
                 tokenizer_name: str = DEFAULT_TOKENIZER,
                 history_tail: int = 60,
                 timeframe: str = DEFAULT_TIMEFRAME,
                 predictor=None) -> ForecastResult:
    """Generate a forecast DISTRIBUTION for an instrument.

    We generate `n_samples` INDEPENDENT paths. The Kronos `sample_count` arg
    AVERAGES internally — that destroys the spread we need — so we instead request
    n_samples independent series via predict_batch (each with sample_count=1) and
    collect the close-price arrays ourselves to form the fan.

    `timeframe` selects daily ('1d') or intraday ('1h'/'15m'/'5m'/'1m'). Kronos
    reads the candle sequence identically; only data interval, future-stamp
    spacing, and vol annualization differ.

    Returns a fully-populated ForecastResult (see dataclass).
    """
    inst = get_instrument(instrument_key)
    tf = timeframe_config(timeframe)
    lookback = int(min(lookback, MAX_CONTEXT))
    n_samples = int(max(2, n_samples))
    pred_len = int(max(1, pred_len))

    # 1. Data
    df = fetch_ohlcv(instrument_key, lookback_days=max(lookback + 60, 200),
                     timeframe=timeframe)
    ticker_used = df.attrs["ticker_used"]
    volume_reliable = df.attrs["volume_is_reliable"]

    if len(df) < lookback:
        lookback = len(df)
    hist = df.tail(lookback).reset_index(drop=True)

    last_close = float(hist["close"].iloc[-1])
    last_history_date = pd.Timestamp(hist["timestamps"].iloc[-1])
    future_ts = _future_timestamps(last_history_date, pred_len, timeframe=timeframe)

    # 2. Build the model input frame. Route to no-volume path when volume is junk.
    use_volume = bool(volume_reliable)
    if use_volume:
        x_cols = ["open", "high", "low", "close", "volume", "amount"]
    else:
        # No-volume path: OHLC only; predictor zero-fills volume + amount.
        x_cols = ["open", "high", "low", "close"]
    x_df = hist[x_cols].copy()
    x_timestamp = hist["timestamps"].copy()

    # 3. Predictor
    if predictor is None:
        predictor = load_predictor(model_name=model_name,
                                   tokenizer_name=tokenizer_name,
                                   device=device,
                                   max_context=MAX_CONTEXT)

    # 4. Generate n_samples INDEPENDENT paths via predict_batch (sample_count=1).
    df_list = [x_df] * n_samples
    xts_list = [x_timestamp] * n_samples
    yts_list = [pd.Series(future_ts)] * n_samples

    pred_dfs = predictor.predict_batch(
        df_list=df_list,
        x_timestamp_list=xts_list,
        y_timestamp_list=yts_list,
        pred_len=pred_len,
        T=T,
        top_k=top_k,
        top_p=top_p,
        sample_count=1,
        verbose=False,
    )
    sample_matrix = np.vstack([p["close"].to_numpy(dtype=float) for p in pred_dfs])

    # 5. Percentile bands from the samples
    p10 = np.percentile(sample_matrix, 10, axis=0)
    p25 = np.percentile(sample_matrix, 25, axis=0)
    median = np.percentile(sample_matrix, 50, axis=0)
    p75 = np.percentile(sample_matrix, 75, axis=0)
    p90 = np.percentile(sample_matrix, 90, axis=0)

    # 6. Risk metrics
    skew = compute_skew_metrics(sample_matrix, last_close)
    rvol = realized_volatility(hist["close"], window=min(30, len(hist) - 1),
                               periods_per_year=tf["periods_per_year"])

    history_for_plot = df.tail(history_tail).reset_index(drop=True)

    return ForecastResult(
        instrument_key=instrument_key,
        display_name=inst.display_name,
        ticker_used=ticker_used,
        used_volume_path=use_volume,
        has_reliable_volume=inst.has_reliable_volume,
        confidence_caveat=inst.confidence_caveat,
        event_sensitive=inst.event_sensitive,
        last_close=last_close,
        last_history_date=last_history_date,
        generated_at=datetime.now(timezone.utc),
        pred_len=pred_len,
        n_samples=n_samples,
        future_timestamps=future_ts,
        p10=p10, p25=p25, median=median, p75=p75, p90=p90,
        sample_matrix=sample_matrix,
        history=history_for_plot,
        realized_vol_annualized=rvol,
        skew_metrics=skew,
        T=T, top_p=top_p, model_name=model_name,
        timeframe=timeframe.lower(),
        timeframe_label=tf["label"],
        is_intraday=tf["intraday"],
    )


# --------------------------------------------------------------------------- #
# Smoke test (SCOPE.md §9 step 2)
# --------------------------------------------------------------------------- #
def _smoke_test():
    print("=" * 70)
    print("forecast_engine smoke test")
    print("=" * 70)
    print(f"KRONOS_DIR = {KRONOS_DIR}")
    print(f"device     = {DEFAULT_DEVICE}")
    print(f"model      = {DEFAULT_MODEL}")
    print("Loading predictor (downloads weights on first run)...")
    predictor = load_predictor(device=DEFAULT_DEVICE)
    print("Predictor loaded.\n")

    for inst in all_instruments():
        print("-" * 70)
        print(f"Instrument: {inst.display_name}  ({inst.key})")
        try:
            res = run_forecast(
                inst.key,
                lookback=200,
                pred_len=5,
                n_samples=5,
                predictor=predictor,
            )
            print(res.summary_text())
            assert res.sample_matrix.shape == (res.n_samples, res.pred_len)
            assert (res.p90 >= res.p10).all(), "p90 should be >= p10"
            vol_note = "no-volume path" if not res.used_volume_path else "volume path"
            print(f"[OK] shape={res.sample_matrix.shape}  ({vol_note})")
        except Exception as exc:  # noqa: BLE001 - smoke test should report all
            print(f"[FAIL] {inst.display_name}: {exc!r}")
        print()


if __name__ == "__main__":
    _smoke_test()
