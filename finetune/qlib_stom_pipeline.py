"""STOM tick DB -> Qlib/Kronos research pipeline helpers.

This module intentionally keeps the first implementation pilot-first:

* it reads the source SQLite database in read-only mode;
* it writes Qlib dump-ready CSV files for optional ``pyqlib`` conversion;
* it writes the pickle split format consumed by ``finetune/dataset.py``;
* it provides a lightweight Qlib-style Top-K score backtest for Kronos
  prediction CSVs.

The produced data artifacts can be large and are not meant to be committed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import pickle
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
FINETUNE_CSV_DIR = PROJECT_ROOT / "finetune_csv"
if str(FINETUNE_CSV_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_CSV_DIR))

from stom_tick_dataset import (  # noqa: E402
    DEFAULT_GROUP_COLUMNS,
    connect_readonly,
    get_table_columns,
    list_stock_tables,
    read_stom_table_as_kline,
)


KRONOS_PICKLE_COLUMNS = ["open", "high", "low", "close", "vol", "amt"]
QLIB_CSV_FIELDS = ["open", "high", "low", "close", "volume", "amount", "money", "factor"]
SUPPORTED_FREQS = {"1s", "1min", "session"}
# ``session`` collapses ALL rows of one (symbol, session) into ONE bar (the
# "daily proxy" of Story B1).  It is a *caveated proxy* for a daily bar — the
# DB is event-triggered + morning-only (~30 min/session), so a session bar is a
# morning-30min bar, NOT a true close-to-close daily bar; cross-session signal
# built on it is confounded by selection bias and is NOT an alpha claim (see
# docs/stom_rl_story_b_daily_data_feasibility_2026-05-27.md).
SESSION_FREQ = "session"
SUPPORTED_SPLIT_STRATEGIES = {"session", "group"}
PYQLIB_PROVIDER_UNSUPPORTED_FREQS = {"1s"}
ExportItem = Tuple[str, str, pd.Timestamp, pd.Timestamp, pd.DataFrame]
STOM_RL_CANONICAL_FEATURES = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "trade_strength",
    "buy_qty_1s",
    "sell_qty_1s",
    "net_buy_qty_1s",
    "bid_ask_imbalance",
    "spread_ticks",
    "amount_delta",
    "turnover_rate",
    "change_rate",
    "market_cap",
    "high_low_mid_change_rate",
    "trade_strength_avg_n",
    "moving_average_n",
    "volatility_n",
    "amount_slope_n",
    "change_rate_slope_n",
]

# Trailing window (bars) for the causal ``trade_strength_avg_n`` rolling mean.
# The window covers ONLY bars <= the current bar (no look-ahead); see
# :func:`build_stom_rl_feature_frame`.
STOM_RL_TRADE_STRENGTH_AVG_WINDOW = 30

# Trailing window (bars, N) for the four causal trend/momentum features
# (``moving_average_n`` 이동평균, ``volatility_n`` 변동성, ``amount_slope_n``
# 거래대금각도, ``change_rate_slope_n`` 등락율각도).  LOCKED at N=10 one-minute
# bars by the Stage-1 pre-registration (docs/stom_rl_1min_stage1_prereg_2026-05-27.md
# §4).  Every window covers ONLY bars <= the current bar (no look-ahead).
STOM_RL_TREND_WINDOW = 10

# Population std (ddof=0) for ``volatility_n`` — LOCKED by Stage-1 pre-registration
# §4 ("변동성 ddof = 0"): deterministic, avoids small-sample inflation at the
# window edge.
STOM_RL_VOLATILITY_DDOF = 0
STOM_RL_FEATURE_MAPPING: Dict[str, Dict[str, Any]] = {
    "trade_strength": {
        "source_columns": ["체결강도", "trade_strength"],
        "formula": "numeric fill 0, clipped to [0, 500]",
    },
    "buy_qty_1s": {
        "source_columns": ["초당매수수량", "buy_qty_1s", "buy_qty"],
        "formula": "numeric fill 0",
    },
    "sell_qty_1s": {
        "source_columns": ["초당매도수량", "sell_qty_1s", "sell_qty"],
        "formula": "numeric fill 0",
    },
    "net_buy_qty_1s": {
        "source_columns": ["buy_qty_1s", "sell_qty_1s"],
        "formula": "buy_qty_1s - sell_qty_1s",
    },
    "bid_ask_imbalance": {
        "source_columns": ["매수총잔량", "매도총잔량", "bid_qty_1", "ask_qty_1"],
        "formula": "bid / max(bid + ask, eps)",
    },
    "spread_ticks": {
        "source_columns": ["매도호가1", "매수호가1", "ask_price_1", "bid_price_1"],
        "formula": "(ask1 - bid1) / tick_size, fallback tick_size=1",
    },
    "amount_delta": {
        "source_columns": ["amount", "거래대금", "초당거래대금"],
        "formula": "group/session first-difference, first row 0",
    },
    "turnover_rate": {
        "source_columns": ["회전율", "turnover_rate"],
        "formula": "numeric fill 0",
    },
    "change_rate": {
        "source_columns": ["등락율", "change_rate"],
        "formula": "numeric fill 0 (same-bar % change, point-in-time)",
    },
    "market_cap": {
        "source_columns": ["시가총액", "market_cap"],
        "formula": "log1p(max(numeric, 0)) to tame the large magnitude",
    },
    "high_low_mid_change_rate": {
        "source_columns": ["고저평균대비등락율", "high_low_mid_change_rate"],
        "formula": "numeric fill 0 (same-bar derived, point-in-time)",
    },
    "trade_strength_avg_n": {
        "source_columns": ["체결강도", "trade_strength"],
        "formula": (
            "trailing causal mean of trade_strength over <= N bars "
            "(rolling(N, min_periods=1).mean(), no look-ahead)"
        ),
    },
    "moving_average_n": {
        "source_columns": ["close"],
        "formula": (
            "이동평균(N): trailing causal mean of close over <= N bars "
            "(rolling(N, min_periods=1).mean(), no look-ahead)"
        ),
    },
    "volatility_n": {
        "source_columns": ["change_rate", "등락율"],
        "formula": (
            "변동성(N): trailing causal population std (ddof=0) of change_rate "
            "over <= N bars (rolling(N, min_periods=1).std(ddof=0), no look-ahead)"
        ),
    },
    "amount_slope_n": {
        "source_columns": ["amount", "초당거래대금"],
        "formula": (
            "거래대금각도: trailing-OLS slope cov(x,y)/var(x) of per-bar SUMMED "
            "amount over <= N bars (rolling(N, min_periods=2), x=bar-index, "
            "trailing-only, no shift(-k)/center)"
        ),
    },
    "change_rate_slope_n": {
        "source_columns": ["change_rate", "등락율"],
        "formula": (
            "등락율각도: trailing-OLS slope cov(x,y)/var(x) of change_rate over "
            "<= N bars (rolling(N, min_periods=2), x=bar-index, trailing-only, "
            "no shift(-k)/center)"
        ),
    },
}


@dataclass
class StomQlibExportConfig:
    db_path: str
    output_dir: str
    max_tables: int = 0
    tables: Optional[List[str]] = None
    lookback_window: int = 300
    predict_window: int = 60
    price_mode: str = "close_only"
    time_start: str = "090000"
    time_end: str = "093000"
    session_start: Optional[str] = None
    session_end: Optional[str] = None
    max_rows_per_group: int = 0
    max_groups: int = 0
    freq: str = "1s"
    regularize_1s: bool = False
    split_by: str = "session"
    horizon_seconds: Optional[int] = None
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15


def _clean_symbol(value: Any) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _instrument_key(symbol: Any, session: Any) -> str:
    """Use symbol+session as an instrument key to prevent cross-session windows."""

    return f"KR{_clean_symbol(symbol)}_{str(session)}"


def _first_present(frame: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _numeric_or_zero(frame: pd.DataFrame, candidates: Sequence[str]) -> pd.Series:
    column = _first_present(frame, candidates)
    if column is None:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _trailing_ols_slope(values: np.ndarray) -> float:
    """Trailing-OLS slope ``cov(x, y) / var(x)`` for one rolling window.

    ``x = [0, 1, ..., k-1]`` is the within-window bar index and ``y`` is the
    window's series values.  Returns ``NaN`` when fewer than 2 points are present
    or ``var(x) == 0`` (a single distinct bar); the caller fills NaN with 0.0.

    The window is supplied by ``rolling(N, min_periods=2)`` which is *trailing
    only* (bars ``<= T``), so this introduces NO look-ahead: row ``T`` never sees
    bar ``T+1``.  No ``shift(-k)``, no ``center=True``, no full-series fit — this
    matches the Stage-1 LOCKED causal slope formula
    (docs/stom_rl_1min_stage1_prereg_2026-05-27.md §4).
    """

    y = np.asarray(values, dtype="float64")
    k = y.size
    if k < 2:
        return float("nan")
    x = np.arange(k, dtype="float64")
    x_mean = x.mean()
    var_x = float(((x - x_mean) ** 2).sum())
    if var_x <= 0.0:
        return float("nan")
    y_mean = y.mean()
    cov_xy = float(((x - x_mean) * (y - y_mean)).sum())
    return cov_xy / var_x


def build_stom_rl_feature_frame(
    frame: pd.DataFrame,
    tick_size: float = 1.0,
    trend_group_keys: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Return a deterministic canonical feature frame for STOM RL.

    The legacy Qlib export keeps ``QLIB_CSV_FIELDS`` unchanged.  This helper is
    an opt-in portfolio/RL feature expansion layer used by tests, future export
    commands, and handoff documentation.

    ``trend_group_keys`` selects the grouping for the sequential/causal features
    (``amount_delta`` first-difference + the trailing means/slopes).  When
    ``None`` (the default) the legacy ``[symbol, session]`` grouping is used, so
    the 1s/1min paths are byte-unchanged: trailing windows never bleed across a
    symbol's *or* a session's boundary.  For Story B1 SESSION bars (one row per
    ``(symbol, session)``) the caller passes ``["symbol"]`` so the trailing trend
    features compute *across the per-symbol session series* (each session is one
    bar) — still trailing-only (no look-ahead), just over the session axis rather
    than within a single session.
    """

    if frame.empty:
        return pd.DataFrame(columns=STOM_RL_CANONICAL_FEATURES)
    out = frame.copy()
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        out[column] = pd.to_numeric(out.get(column, 0.0), errors="coerce").fillna(0.0)

    out["trade_strength"] = _numeric_or_zero(out, ["체결강도", "trade_strength"]).clip(0.0, 500.0)
    out["buy_qty_1s"] = _numeric_or_zero(out, ["초당매수수량", "buy_qty_1s", "buy_qty"])
    out["sell_qty_1s"] = _numeric_or_zero(out, ["초당매도수량", "sell_qty_1s", "sell_qty"])
    out["net_buy_qty_1s"] = out["buy_qty_1s"] - out["sell_qty_1s"]

    bid = _numeric_or_zero(out, ["매수총잔량", "bid_qty_1", "bid_qty"])
    ask = _numeric_or_zero(out, ["매도총잔량", "ask_qty_1", "ask_qty"])
    out["bid_ask_imbalance"] = bid / np.maximum(bid + ask, 1e-9)

    bid_price = _numeric_or_zero(out, ["매수호가1", "bid_price_1", "bid_price"])
    ask_price = _numeric_or_zero(out, ["매도호가1", "ask_price_1", "ask_price"])
    missing_quote = (bid_price <= 0) | (ask_price <= 0)
    bid_price = bid_price.mask(missing_quote, out["close"])
    ask_price = ask_price.mask(missing_quote, out["close"])
    out["spread_ticks"] = (ask_price - bid_price).clip(lower=0.0) / max(float(tick_size), 1e-9)

    if trend_group_keys is None:
        group_keys = [column for column in ["symbol", "session"] if column in out.columns]
    else:
        group_keys = [column for column in trend_group_keys if column in out.columns]
    if group_keys:
        out["amount_delta"] = out.groupby(group_keys, sort=False)["amount"].diff().fillna(0.0)
    else:
        out["amount_delta"] = out["amount"].diff().fillna(0.0)
    out["turnover_rate"] = _numeric_or_zero(out, ["회전율", "turnover_rate"])

    # Stage C feature expansion (C-0 probe confirmed dense direct DB columns).
    out["change_rate"] = _numeric_or_zero(out, ["등락율", "change_rate"])
    # ``시가총액`` (market cap) spans 2+ orders of magnitude; log1p keeps it on a
    # comparable scale to the other features (matches the "log" normalization
    # guidance) while staying finite for the non-negative magnitudes in the DB.
    market_cap_raw = _numeric_or_zero(out, ["시가총액", "market_cap"]).clip(lower=0.0)
    out["market_cap"] = np.log1p(market_cap_raw)
    out["high_low_mid_change_rate"] = _numeric_or_zero(
        out, ["고저평균대비등락율", "high_low_mid_change_rate"]
    )

    # Causal trailing mean of trade strength over <= N bars (NO look-ahead): a
    # row at index T uses only rows in [T-N+1, T].  ``rolling(...).mean()`` is
    # backward-only by construction; grouping per symbol/session prevents the
    # window from bleeding across instruments or sessions.
    window = int(STOM_RL_TRADE_STRENGTH_AVG_WINDOW)
    if group_keys:
        out["trade_strength_avg_n"] = (
            out.groupby(group_keys, sort=False)["trade_strength"]
            .transform(lambda s: s.rolling(window, min_periods=1).mean())
        )
    else:
        out["trade_strength_avg_n"] = (
            out["trade_strength"].rolling(window, min_periods=1).mean()
        )

    # ------------------------------------------------------------------
    # Causal trend/momentum features (이동평균/변동성/거래대금각도/등락율각도).
    # All four are trailing-only (window in [T-N+1, T], NO shift(-k)/center) and
    # grouped per symbol/session so the window never bleeds across instruments or
    # sessions.  N and the 변동성 ddof are LOCKED by Stage-1 pre-registration.
    # Level features use min_periods=1; slope features use min_periods=2 (a slope
    # needs >=2 points) and their first-bar NaN is filled to 0.0 by the closing
    # replace/fillna — no look-ahead is introduced.
    # ------------------------------------------------------------------
    trend_window = int(STOM_RL_TREND_WINDOW)
    ddof = int(STOM_RL_VOLATILITY_DDOF)

    def _ma(series: pd.Series) -> pd.Series:
        return series.rolling(trend_window, min_periods=1).mean()

    def _vol(series: pd.Series) -> pd.Series:
        return series.rolling(trend_window, min_periods=1).std(ddof=ddof)

    def _slope(series: pd.Series) -> pd.Series:
        return series.rolling(trend_window, min_periods=2).apply(
            _trailing_ols_slope, raw=True
        )

    if group_keys:
        grouped = out.groupby(group_keys, sort=False)
        out["moving_average_n"] = grouped["close"].transform(_ma)
        out["volatility_n"] = grouped["change_rate"].transform(_vol)
        out["amount_slope_n"] = grouped["amount"].transform(_slope)
        out["change_rate_slope_n"] = grouped["change_rate"].transform(_slope)
    else:
        out["moving_average_n"] = _ma(out["close"])
        out["volatility_n"] = _vol(out["change_rate"])
        out["amount_slope_n"] = _slope(out["amount"])
        out["change_rate_slope_n"] = _slope(out["change_rate"])

    return out[STOM_RL_CANONICAL_FEATURES].replace([np.inf, -np.inf], 0.0).fillna(0.0)


# ---------------------------------------------------------------------------
# STOM RL feature export (Page 7) — opt-in, non-invasive path.
#
# The legacy ``export`` subcommand and ``QLIB_CSV_FIELDS`` stay unchanged so
# existing Kronos/Qlib consumers are not affected.  This path reads ONE symbol
# table for a small time window, decodes the source column names, maps them to
# the inputs of :func:`build_stom_rl_feature_frame`, and emits the canonical
# RL features plus a missing/scale report.  It never performs a full DB scan.
# ---------------------------------------------------------------------------

# DB-source columns required to compute the canonical RL features.  Korean
# names are stored as UTF-8 in the STOM tick DB and are returned correctly by
# sqlite3's default ``text_factory`` (no cp949 round-trip needed for this DB).
STOM_RL_SOURCE_COLUMNS: Dict[str, List[str]] = {
    "timestamp": ["index", "timestamps", "timestamp"],
    "close": ["현재가", "종가", "close"],
    "open": ["시가", "open"],
    "high": ["고가", "high"],
    "low": ["저가", "low"],
    "buy_qty_1s": ["초당매수수량"],
    "sell_qty_1s": ["초당매도수량"],
    "체결강도": ["체결강도"],
    "amount": ["초당거래대금", "거래대금", "당일거래대금"],
    "회전율": ["회전율"],
    "매수총잔량": ["매수총잔량"],
    "매도총잔량": ["매도총잔량"],
    "매수호가1": ["매수호가1"],
    "매도호가1": ["매도호가1"],
    "등락율": ["등락율"],
    "시가총액": ["시가총액"],
    "고저평균대비등락율": ["고저평균대비등락율"],
}


def _sqlite_quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _decode_table_columns(conn: Any, table_name: str) -> List[str]:
    """Return source column names, retrying with explicit decoding if needed.

    The STOM tick DB stores Korean column names as UTF-8, which sqlite3 decodes
    correctly by default.  As a defensive fallback (other dumps may differ) we
    re-read the raw bytes and try utf-8 then cp949 when the default names look
    corrupted (contain the Unicode replacement character).
    """

    names = get_table_columns(conn, table_name)
    if not any("�" in str(name) for name in names):
        return list(names)

    raw_factory = conn.text_factory
    try:
        conn.text_factory = bytes
        raw_rows = conn.execute(
            f"PRAGMA table_info({_sqlite_quote_ident(table_name)})"
        ).fetchall()
    finally:
        conn.text_factory = raw_factory

    decoded: List[str] = []
    for row in raw_rows:
        raw_name = row[1]
        if isinstance(raw_name, bytes):
            for encoding in ("utf-8", "cp949"):
                try:
                    decoded.append(raw_name.decode(encoding))
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                decoded.append(raw_name.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(raw_name))
    return decoded


def _resolve_source_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def read_stom_table_rl_source(
    conn: Any,
    table_name: str,
    session: Optional[str] = None,
    time_start: str = "090000",
    time_end: str = "093000",
    max_rows: int = 0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Read ONE STOM symbol table window into RL feature-builder input columns.

    Returns a frame carrying ``symbol``/``session``/``timestamp`` plus the
    DB-named source columns expected by :func:`build_stom_rl_feature_frame`.
    The query is bounded by the time window (and optional ``max_rows``) so it
    never scans the whole table — full-DB scans are out of scope for Page 7.
    """

    source_columns = _decode_table_columns(conn, table_name)
    encoding_ok = not any("�" in str(name) for name in source_columns)
    resolved: Dict[str, Optional[str]] = {
        target: _resolve_source_column(source_columns, candidates)
        for target, candidates in STOM_RL_SOURCE_COLUMNS.items()
    }
    timestamp_col = resolved.get("timestamp")
    close_col = resolved.get("close")
    if not timestamp_col or not close_col:
        missing = [k for k in ("timestamp", "close") if not resolved.get(k)]
        raise ValueError(f"Table {table_name} is missing required columns: {missing}")

    selected = sorted({col for col in resolved.values() if col})
    select_clause = ", ".join(_sqlite_quote_ident(col) for col in selected)
    order_col = _sqlite_quote_ident(timestamp_col)
    where_clauses = []
    params: List[Any] = []
    if session:
        if len(session) != 8 or not session.isdigit():
            raise ValueError(f"session must be YYYYMMDD, got: {session}")
        prefix_expr = f"substr(CAST({order_col} AS TEXT), 1, 8)"
        where_clauses.append(f"{prefix_expr} = ?")
        params.append(session)
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    limit_sql = ""
    if max_rows and max_rows > 0:
        # Bound the read defensively even before the in-pandas time filter.
        limit_sql = f" LIMIT {int(max_rows) * 4 + 4096}"
    query = (
        f"SELECT {select_clause} FROM {_sqlite_quote_ident(table_name)}"
        f"{where_sql} ORDER BY {order_col}{limit_sql}"
    )
    raw = pd.read_sql_query(query, conn, params=params)

    timestamps = pd.to_datetime(
        pd.to_numeric(raw[timestamp_col], errors="coerce").astype("Int64").astype(str),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    frame = pd.DataFrame({"timestamp": timestamps})
    frame["symbol"] = _clean_symbol(table_name)

    close = pd.to_numeric(raw[close_col], errors="coerce")
    frame["close"] = close
    for ohlc in ("open", "high", "low"):
        col = resolved.get(ohlc)
        frame[ohlc] = pd.to_numeric(raw[col], errors="coerce") if col else close

    buy_col = resolved.get("buy_qty_1s")
    sell_col = resolved.get("sell_qty_1s")
    buy_qty = pd.to_numeric(raw[buy_col], errors="coerce").fillna(0.0) if buy_col else pd.Series(0.0, index=raw.index)
    sell_qty = pd.to_numeric(raw[sell_col], errors="coerce").fillna(0.0) if sell_col else pd.Series(0.0, index=raw.index)
    frame["초당매수수량"] = buy_qty
    frame["초당매도수량"] = sell_qty
    frame["volume"] = buy_qty + sell_qty

    amount_col = resolved.get("amount")
    frame["amount"] = pd.to_numeric(raw[amount_col], errors="coerce").fillna(0.0) if amount_col else frame["volume"] * close.fillna(0.0)

    for passthrough in (
        "체결강도",
        "회전율",
        "매수총잔량",
        "매도총잔량",
        "매수호가1",
        "매도호가1",
        "등락율",
        "시가총액",
        "고저평균대비등락율",
    ):
        col = resolved.get(passthrough)
        if col:
            frame[passthrough] = pd.to_numeric(raw[col], errors="coerce")

    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame = frame[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)]

    hhmmss = frame["timestamp"].dt.strftime("%H%M%S")
    if time_start:
        frame = frame[hhmmss >= time_start]
    if time_end:
        frame = frame[hhmmss <= time_end]
    frame["session"] = frame["timestamp"].dt.strftime("%Y%m%d")
    frame = frame.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    if max_rows and max_rows > 0:
        frame = frame.head(max_rows)
    frame = frame.reset_index(drop=True)

    report = {
        "table": table_name,
        "symbol": _clean_symbol(table_name),
        "source_column_count": len(source_columns),
        "column_encoding": "utf-8" if encoding_ok else "decoded-fallback",
        "encoding_confirmed": bool(encoding_ok),
        "resolved_source_columns": {k: v for k, v in resolved.items()},
        "unresolved_targets": [k for k, v in resolved.items() if v is None],
        "row_count": int(len(frame)),
    }
    return frame, report


# ---------------------------------------------------------------------------
# Net-new RL-path 1-minute resampler (Stage 2, R1).
#
# This is NOT ``_resample_group`` (which is ``"timestamps"``-keyed, OHLCV-only,
# and would KeyError / silently drop the 12 non-OHLCV RL passthrough columns —
# manufacturing all-zero features and a FALSE null).  This resampler keys on
# ``"timestamp"`` (the RL source frame's key, matching
# :func:`read_stom_table_rl_source`) and aggregates EVERY source column the
# feature builder reads, per the Stage-1 LOCKED per-column aggregation table
# (docs/stom_rl_1min_stage1_prereg_2026-05-27.md §5).  It runs on the RL source
# frame BEFORE :func:`build_stom_rl_feature_frame`, so all derived features
# (amount_delta, net_buy_qty_1s, the trailing means/slopes) recompute correctly
# on the 1-minute bars.
# ---------------------------------------------------------------------------

# Per-column 1-minute aggregation, LOCKED by Stage-1 §5.
#   OHLC: open=first, high=max, low=min, close=last
#   flow -> SUM: 초당매수수량, 초당매도수량, volume (derived = buy+sell), amount
#       (amount = 초당거래대금 PER-SECOND, Stage-1 §2 -> SUM, no cumulative branch)
#   order-book + rate/snapshot -> LAST
STOM_RL_RESAMPLE_AGG: Dict[str, str] = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    # flow -> SUM
    "초당매수수량": "sum",
    "초당매도수량": "sum",
    # ``volume`` is DERIVED in read_stom_table_rl_source (volume = buy+sell);
    # summing the per-second derived volume over a 1-min bucket is correct.
    "volume": "sum",
    # ``amount`` resolves to 초당거래대금 (per-second flow, Stage-1 §2) -> SUM.
    "amount": "sum",
    # order-book -> LAST (snapshot at the last second in the bucket)
    "매수총잔량": "last",
    "매도총잔량": "last",
    "매수호가1": "last",
    "매도호가1": "last",
    # rate / snapshot -> LAST
    "등락율": "last",
    "회전율": "last",
    "시가총액": "last",
    "고저평균대비등락율": "last",
    "체결강도": "last",
}


def resample_stom_rl_source_frame(frame: pd.DataFrame, freq: str = "1s") -> pd.DataFrame:
    """Resample an RL *source* frame to the requested bar frequency.

    ``frame`` is the output of :func:`read_stom_table_rl_source` — keyed on
    ``"timestamp"`` with ``symbol``/``session`` plus the DB-named source columns.
    For ``freq == "1s"`` the frame is returned unchanged (the 1s path is
    byte-identical, so all existing tests stay green).  For ``freq == "1min"``
    each ``(symbol, session)`` group is floored to 1-minute buckets
    (``floor("min")``, bucket-START labeling) and every present source column is
    aggregated per :data:`STOM_RL_RESAMPLE_AGG` (the Stage-1 LOCKED table); the
    resulting ``"timestamp"`` is the bucket start, so bar ``T`` carries NO value
    from bar ``T+1`` (coheres with the grid-agnostic T+1 fill).

    For ``freq == "session"`` (Story B1 "daily proxy") ALL rows of one
    ``(symbol, session)`` collapse into ONE bar using the SAME LOCKED per-column
    aggregation (OHLC=first/max/min/last, flow/amount=SUM, book/rate=LAST).  The
    bucket is the ``session`` itself, so there is exactly one bar per
    ``(symbol, session)``; the resulting ``"timestamp"`` is set to the session
    date (midnight of ``YYYYMMDD``) so cross-session bars of *different* symbols
    align on a common session-date axis (the cross-session panel grid).  This is
    a CAVEATED PROXY: the session window is the recorded morning ~30 min, NOT a
    true close-to-close day, and symbols appear only on dates they triggered
    recording (selection bias).  Causal trend features still compute trailing
    across the per-symbol SESSION series downstream (no look-ahead).

    Columns not present in the input are skipped; columns present but absent from
    the agg table fall back to ``last`` (a point-in-time snapshot, never a future
    value).
    """

    if freq not in SUPPORTED_FREQS:
        raise ValueError(f"freq must be one of {sorted(SUPPORTED_FREQS)}")
    if freq == "1s" or frame.empty or "timestamp" not in frame.columns:
        return frame

    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    work = work.dropna(subset=["timestamp"])
    if work.empty:
        return work.reset_index(drop=True)

    if freq == SESSION_FREQ:
        # ONE bar per (symbol, session): the bucket IS the calendar day of the
        # session.  Use the session date (parsed from the YYYYMMDD ``session``
        # string when present, else the timestamp's day) so different symbols'
        # session bars land on a SHARED session-date axis for the cross-session
        # panel.  ``floor("D")`` of the per-row timestamp would also collapse to
        # the day, but deriving from ``session`` keeps the proxy honest when a
        # row's clock time and its session label disagree.
        if "session" in work.columns:
            session_day = pd.to_datetime(
                work["session"].astype(str), format="%Y%m%d", errors="coerce"
            )
            work["__bucket__"] = session_day.fillna(work["timestamp"].dt.floor("D"))
        else:
            work["__bucket__"] = work["timestamp"].dt.floor("D")
    else:
        work["__bucket__"] = work["timestamp"].dt.floor("min")
    group_keys = [c for c in ("symbol", "session") if c in work.columns]
    value_cols = [
        c for c in work.columns if c not in (*group_keys, "timestamp", "__bucket__")
    ]
    agg_map = {
        col: STOM_RL_RESAMPLE_AGG.get(col, "last") for col in value_cols
    }

    grouped = work.sort_values("timestamp", kind="mergesort").groupby(
        [*group_keys, "__bucket__"], sort=True
    )
    resampled = grouped.agg(agg_map).reset_index()
    # The bucket start IS the 1-min bar timestamp (bucket-START labeling).
    resampled = resampled.rename(columns={"__bucket__": "timestamp"})
    ordered = ["timestamp", *group_keys, *value_cols]
    resampled = resampled[[c for c in ordered if c in resampled.columns]]
    return resampled.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _missing_scale_report(features: pd.DataFrame) -> Dict[str, Any]:
    column_stats: Dict[str, Any] = {}
    total = int(len(features))
    has_nan = False
    has_inf = False
    for column in features.columns:
        series = pd.to_numeric(features[column], errors="coerce")
        null_count = int(series.isna().sum())
        inf_count = int(np.isinf(series.to_numpy(dtype="float64", na_value=np.nan)).sum())
        has_nan = has_nan or null_count > 0
        has_inf = has_inf or inf_count > 0
        finite = series.replace([np.inf, -np.inf], np.nan).dropna()
        column_stats[column] = {
            "null_rate": (null_count / total) if total else 0.0,
            "null_count": null_count,
            "inf_count": inf_count,
            "min": float(finite.min()) if not finite.empty else None,
            "max": float(finite.max()) if not finite.empty else None,
            "mean": float(finite.mean()) if not finite.empty else None,
        }
    return {
        "row_count": total,
        "feature_count": int(features.shape[1]),
        "has_nan": has_nan,
        "has_inf": has_inf,
        "nan_inf_clean": (not has_nan) and (not has_inf),
        "columns": column_stats,
    }


def export_stom_rl_features(
    db_path: os.PathLike | str,
    output_dir: os.PathLike | str,
    table: str,
    session: Optional[str] = None,
    time_start: str = "090000",
    time_end: str = "093000",
    max_rows: int = 0,
    tick_size: float = 1.0,
    freq: str = "1s",
) -> Dict[str, Any]:
    """Export the canonical STOM RL features for ONE symbol/time window.

    Writes ``<symbol>_rl_features.csv`` (the canonical features plus
    ``timestamp``/``symbol``/``session`` keys) and a missing/scale report JSON.
    The legacy Qlib export and ``QLIB_CSV_FIELDS`` are left untouched.

    ``freq`` is accepted for parity with the live feed path (default ``"1s"``
    leaves the frame unchanged).  NOTE: this CSV emitter is NOT the feed path —
    the live walk-forward feed resamples inside :func:`build_panel_from_db`
    (``stom_rl/panel_join.py``).  ``freq`` here only affects the standalone CSV.
    """

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect_readonly(db_path)
    try:
        source_frame, source_report = read_stom_table_rl_source(
            conn,
            table,
            session=session,
            time_start=time_start,
            time_end=time_end,
            max_rows=max_rows,
        )
    finally:
        conn.close()

    if source_frame.empty:
        raise ValueError(
            f"No rows for table={table} session={session} window={time_start}-{time_end}. "
            "Widen the time window or pick a session with data."
        )

    # Resample the RL SOURCE frame BEFORE the feature builder so derived features
    # (amount_delta, net_buy_qty_1s, trailing means/slopes) recompute on bars.
    source_frame = resample_stom_rl_source_frame(source_frame, freq=freq)
    features = build_stom_rl_feature_frame(source_frame, tick_size=tick_size)
    keyed = pd.concat(
        [source_frame[["timestamp", "symbol", "session"]].reset_index(drop=True), features.reset_index(drop=True)],
        axis=1,
    )
    csv_name = f"{source_report['symbol']}_rl_features.csv"
    csv_path = out_dir / csv_name
    keyed.to_csv(csv_path, index=False, encoding="utf-8-sig")

    scale_report = _missing_scale_report(features)
    report = {
        "mode": "stom_rl_feature_export",
        "db_path": str(db_path),
        "output_dir": str(out_dir),
        "csv_path": str(csv_path),
        "canonical_features": list(STOM_RL_CANONICAL_FEATURES),
        "config": {
            "table": table,
            "session": session,
            "time_start": time_start,
            "time_end": time_end,
            "max_rows": max_rows,
            "tick_size": tick_size,
            "freq": freq,
        },
        "source": source_report,
        "scale": scale_report,
    }
    _write_json(out_dir / "stom_rl_feature_report.json", report)
    return report


def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    total = train_ratio + val_ratio + test_ratio
    if total <= 0:
        raise ValueError("At least one split ratio must be positive.")
    if any(r < 0 for r in [train_ratio, val_ratio, test_ratio]):
        raise ValueError("Split ratios must be non-negative.")
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"Split ratios must sum to 1.0; got {total:.6f}")


def _resample_group(group: pd.DataFrame, freq: str) -> pd.DataFrame:
    if freq not in SUPPORTED_FREQS:
        raise ValueError(f"freq must be one of {sorted(SUPPORTED_FREQS)}")
    group = group.sort_values("timestamps").copy()
    if freq == "1s":
        return group

    # 1min aggregation keeps standard OHLCV semantics and sums flow fields.
    group["bucket"] = group["timestamps"].dt.floor("min")
    out = (
        group.groupby(["symbol", "session", "bucket"], sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        )
        .reset_index()
        .rename(columns={"bucket": "timestamps"})
    )
    return out


def _split_count(total: int, train_ratio: float, val_ratio: float, test_ratio: float) -> Tuple[int, int]:
    train_end = int(total * train_ratio)
    val_end = int(total * (train_ratio + val_ratio))

    if train_ratio > 0 and train_end == 0 and total > 0:
        train_end = 1
    if val_ratio > 0 and val_end <= train_end and total > train_end:
        val_end = train_end + 1
    if test_ratio > 0 and val_end >= total and total > train_end:
        val_end = max(train_end, total - 1)
    return train_end, val_end


def _split_items(
    items: Sequence[ExportItem],
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    split_by: str = "session",
) -> Dict[str, List[ExportItem]]:
    _validate_ratios(train_ratio, val_ratio, test_ratio)
    if split_by not in SUPPORTED_SPLIT_STRATEGIES:
        raise ValueError(f"split_by must be one of {sorted(SUPPORTED_SPLIT_STRATEGIES)}")

    ordered = sorted(items, key=lambda item: (item[2], item[0]))
    if split_by == "group":
        train_end, val_end = _split_count(len(ordered), train_ratio, val_ratio, test_ratio)
        return {
            "train": ordered[:train_end],
            "val": ordered[train_end:val_end],
            "test": ordered[val_end:],
        }

    sessions = sorted({session for _, session, _, _, _ in ordered})
    train_end, val_end = _split_count(len(sessions), train_ratio, val_ratio, test_ratio)
    split_sessions = {
        "train": set(sessions[:train_end]),
        "val": set(sessions[train_end:val_end]),
        "test": set(sessions[val_end:]),
    }

    return {
        split_name: [item for item in ordered if item[1] in session_set]
        for split_name, session_set in split_sessions.items()
    }


def _split_session_summary(split_items: Dict[str, List[ExportItem]]) -> Dict[str, List[str]]:
    return {
        split_name: sorted({session for _, session, _, _, _ in split_rows})
        for split_name, split_rows in split_items.items()
    }


def _session_time(session: Any, hhmmss: Optional[str]) -> Optional[pd.Timestamp]:
    if not hhmmss:
        return None
    text = str(hhmmss)
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"Expected HHMMSS time, got: {hhmmss}")
    return pd.to_datetime(f"{session}{text}", format="%Y%m%d%H%M%S", errors="raise")


def _regularize_group_to_1s(
    group: pd.DataFrame,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Reindex a symbol/session group to a true one-second grid without leading look-ahead fill."""

    if group.empty:
        return group.copy(), {"input_rows": 0, "output_rows": 0, "inserted_rows": 0}

    ordered = group.sort_values("timestamps").drop_duplicates("timestamps", keep="last").copy()
    session = str(ordered["session"].iloc[0])
    start_ts = _session_time(session, time_start) or ordered["timestamps"].min()
    end_ts = _session_time(session, time_end) or ordered["timestamps"].max()
    start_ts = max(pd.Timestamp(start_ts), pd.Timestamp(ordered["timestamps"].min()))
    end_ts = min(pd.Timestamp(end_ts), pd.Timestamp(ordered["timestamps"].max()) if not time_end else pd.Timestamp(end_ts))
    if end_ts < start_ts:
        return ordered, {
            "input_rows": int(len(group)),
            "output_rows": int(len(ordered)),
            "inserted_rows": 0,
            "warning": "regularize_1s skipped because computed end is before start",
        }

    full_index = pd.date_range(start=start_ts, end=end_ts, freq="1s")
    indexed = ordered.set_index("timestamps").reindex(full_index)
    indexed.index.name = "timestamps"
    indexed["symbol"] = indexed["symbol"].ffill()
    indexed["session"] = indexed["session"].ffill()
    price_columns = ["open", "high", "low", "close"]
    indexed[price_columns] = indexed[price_columns].ffill()
    indexed[["volume", "amount"]] = indexed[["volume", "amount"]].fillna(0.0)
    indexed = indexed.dropna(subset=["symbol", "session", *price_columns])
    out = indexed.reset_index()
    return out[DEFAULT_GROUP_COLUMNS + ["timestamps"] + ["open", "high", "low", "close", "volume", "amount"]], {
        "input_rows": int(len(ordered)),
        "output_rows": int(len(out)),
        "inserted_rows": int(max(len(out) - len(ordered), 0)),
        "start_timestamp": None if out.empty else str(out["timestamps"].iloc[0]),
        "end_timestamp": None if out.empty else str(out["timestamps"].iloc[-1]),
    }


def _to_kronos_pickle_frame(group: pd.DataFrame) -> pd.DataFrame:
    out = group[["timestamps", "open", "high", "low", "close", "volume", "amount"]].copy()
    out = out.rename(columns={"timestamps": "datetime", "volume": "vol", "amount": "amt"})
    out["datetime"] = pd.to_datetime(out["datetime"])
    for column in KRONOS_PICKLE_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["datetime", *KRONOS_PICKLE_COLUMNS]).sort_values("datetime")
    return out.set_index("datetime")[KRONOS_PICKLE_COLUMNS]


def _to_qlib_dump_csv_frame(instrument: str, group: pd.DataFrame) -> pd.DataFrame:
    out = group[["timestamps", "open", "high", "low", "close", "volume", "amount"]].copy()
    out = out.rename(columns={"timestamps": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    out["symbol"] = instrument
    out["money"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0.0)
    out["factor"] = 1.0
    return out[["symbol", "date", *QLIB_CSV_FIELDS]]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def check_qlib_environment(dump_bin_script: Optional[Path] = None) -> Dict[str, Any]:
    """Return pyqlib/dump_bin readiness without requiring pyqlib to be installed."""

    qlib_spec = importlib.util.find_spec("qlib")
    qlib_version = None
    qlib_error = None
    if qlib_spec is not None:
        try:
            import qlib  # type: ignore

            qlib_version = getattr(qlib, "__version__", "unknown")
        except Exception as exc:  # pragma: no cover - depends on local pyqlib install
            qlib_error = repr(exc)

    candidates: List[Path] = []
    if dump_bin_script is not None:
        candidates.append(Path(dump_bin_script))
    env_dump_bin = os.environ.get("QLIB_DUMP_BIN_SCRIPT")
    if env_dump_bin:
        candidates.append(Path(env_dump_bin))
    if qlib_spec is not None and qlib_spec.origin:
        qlib_origin = Path(qlib_spec.origin).resolve()
        candidates.extend(
            [
                qlib_origin.parent / "scripts" / "dump_bin.py",
                qlib_origin.parent.parent / "scripts" / "dump_bin.py",
            ]
        )
    candidates.extend(
        [
            PROJECT_ROOT / "scripts" / "dump_bin.py",
            PROJECT_ROOT / "qlib" / "scripts" / "dump_bin.py",
            PROJECT_ROOT / ".omx" / "external" / "qlib" / "scripts" / "dump_bin.py",
        ]
    )
    existing_script = next((path.resolve() for path in candidates if path.exists()), None)

    return {
        "qlib_installed": qlib_spec is not None and qlib_error is None,
        "qlib_origin": None if qlib_spec is None else qlib_spec.origin,
        "qlib_version": qlib_version,
        "qlib_error": qlib_error,
        "dump_bin_script_found": existing_script is not None,
        "dump_bin_script": None if existing_script is None else str(existing_script),
        "recommended_install_command": "python -m pip install pyqlib",
        "recommended_dump_bin_source": "Clone microsoft/qlib or point --dump-bin-script to qlib/scripts/dump_bin.py",
    }


def build_dump_bin_command(
    csv_path: Path,
    qlib_dir: Path,
    dump_bin_script: Optional[Path] = None,
    include_fields: Optional[Sequence[str]] = None,
    date_field_name: str = "date",
    symbol_field_name: str = "symbol",
    freq: Optional[str] = None,
) -> List[str]:
    script = Path(dump_bin_script) if dump_bin_script else Path("scripts") / "dump_bin.py"
    command = [
        sys.executable,
        str(script),
        "dump_all",
        "--data_path",
        str(csv_path),
        "--qlib_dir",
        str(qlib_dir),
        "--date_field_name",
        date_field_name,
        "--symbol_field_name",
        symbol_field_name,
        "--include_fields",
        ",".join(include_fields or QLIB_CSV_FIELDS),
    ]
    if freq:
        command.extend(["--freq", freq])
    return command


def run_dump_bin_from_report(
    export_report_path: Path,
    qlib_dir: Optional[Path] = None,
    dump_bin_script: Optional[Path] = None,
    execute: bool = False,
    freq: Optional[str] = None,
) -> Dict[str, Any]:
    report = json.loads(Path(export_report_path).read_text(encoding="utf-8"))
    csv_path = Path(report["qlib_csv_dir"])
    target_dir = Path(qlib_dir) if qlib_dir else Path(report["output_dir"]) / "qlib_bin"
    effective_freq = freq or report.get("config", {}).get("freq")
    command = build_dump_bin_command(
        csv_path=csv_path,
        qlib_dir=target_dir,
        dump_bin_script=dump_bin_script,
        include_fields=QLIB_CSV_FIELDS,
        freq=effective_freq,
    )
    result: Dict[str, Any] = {
        "mode": "qlib_dump_bin",
        "export_report_path": str(export_report_path),
        "csv_path": str(csv_path),
        "qlib_dir": str(target_dir),
        "command": command,
        "command_text": _format_command(command),
        "executed": execute,
    }
    if not execute:
        result["status"] = "dry_run"
        return result

    script = Path(command[1])
    if not script.is_absolute():
        script = PROJECT_ROOT / script
        command[1] = str(script)
        result["command"] = command
        result["command_text"] = _format_command(command)
    if not script.exists():
        raise FileNotFoundError(
            f"dump_bin.py not found: {script}. "
            "Install/clone microsoft/qlib and pass --dump-bin-script, or run qlib-env-check first."
        )
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    result.update(
        {
            "returncode": completed.returncode,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
            "status": "ok" if completed.returncode == 0 else "failed",
        }
    )
    if completed.returncode != 0:
        raise RuntimeError(f"dump_bin failed with exit code {completed.returncode}: {stderr[-1000:]}")
    return result


def smoke_qlib_provider(provider_uri: Path, region: str = "cn", freq: str = "day") -> Dict[str, Any]:
    """Initialize pyqlib provider and load a small calendar sample."""

    if freq.lower() in PYQLIB_PROVIDER_UNSUPPORTED_FREQS:
        raise ValueError(
            "pyqlib provider does not support second-level freq such as '1s'. "
            "Use --freq 1min for Qlib provider smoke, or use the generated "
            "processed_datasets pickles for Kronos 1-second fine-tuning."
        )

    try:
        import qlib  # type: ignore
        from qlib.config import REG_CN, REG_US  # type: ignore
        from qlib.data import D  # type: ignore
    except Exception as exc:
        raise RuntimeError("pyqlib is not installed or cannot be imported. Run: python -m pip install pyqlib") from exc

    region_map = {"cn": REG_CN, "us": REG_US}
    qlib.init(provider_uri=str(provider_uri), region=region_map.get(region.lower(), REG_CN))
    calendar = D.calendar(freq=freq)
    sample = [str(item) for item in calendar[: min(len(calendar), 5)]]
    return {
        "mode": "qlib_provider_smoke",
        "provider_uri": str(provider_uri),
        "region": region,
        "freq": freq,
        "calendar_count": int(len(calendar)),
        "calendar_sample": sample,
    }


def export_stom_to_qlib(config: StomQlibExportConfig) -> Dict[str, Any]:
    """Export STOM DB rows to Qlib dump-ready CSV and Kronos QlibDataset pickles."""

    predict_window = config.horizon_seconds if config.horizon_seconds is not None else config.predict_window
    if config.horizon_seconds is not None and config.freq != "1s":
        raise ValueError("--horizon-seconds is only valid for --freq 1s exports.")
    if config.regularize_1s and config.freq != "1s":
        raise ValueError("--regularize-1s is only valid with --freq 1s.")
    min_rows = config.lookback_window + predict_window + 1
    output_dir = Path(config.output_dir)
    qlib_csv_dir = output_dir / "qlib_csv"
    processed_dir = output_dir / "processed_datasets"
    meta_dir = output_dir / "meta"
    for directory in [qlib_csv_dir, processed_dir, meta_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    conn = connect_readonly(config.db_path)
    items: List[ExportItem] = []
    table_reports: List[Dict[str, Any]] = []
    warnings: List[str] = []
    grid_summary = {"regularized_groups": 0, "inserted_rows": 0}
    try:
        selected_tables = list(config.tables) if config.tables else list_stock_tables(conn, max_tables=None)
        if config.max_tables and config.max_tables > 0:
            selected_tables = selected_tables[: config.max_tables]

        for table in selected_tables:
            if config.max_groups and len(items) >= config.max_groups:
                break
            try:
                frame, mapping = read_stom_table_as_kline(
                    conn,
                    table,
                    price_mode=config.price_mode,
                    time_start=config.time_start,
                    time_end=config.time_end,
                    session_start=config.session_start,
                    session_end=config.session_end,
                )
                mapping_warnings = mapping.get("warnings", [])
                warnings.extend(str(w) for w in mapping_warnings)
                written_groups = 0
                written_rows = 0
                skipped_groups = 0
                table_grid_inserted_rows = 0
                for (symbol, session), group in frame.groupby(DEFAULT_GROUP_COLUMNS, sort=True):
                    if config.max_groups and len(items) >= config.max_groups:
                        break
                    group = _resample_group(group, config.freq)
                    if config.regularize_1s:
                        group, group_grid = _regularize_group_to_1s(
                            group,
                            time_start=config.time_start,
                            time_end=config.time_end,
                        )
                        grid_summary["regularized_groups"] += 1
                        grid_summary["inserted_rows"] += int(group_grid.get("inserted_rows", 0))
                        table_grid_inserted_rows += int(group_grid.get("inserted_rows", 0))
                    if config.max_rows_per_group and config.max_rows_per_group > 0:
                        group = group.head(config.max_rows_per_group)
                    if len(group) < min_rows:
                        skipped_groups += 1
                        continue

                    instrument = _instrument_key(symbol, session)
                    group = group.sort_values("timestamps").reset_index(drop=True)
                    qlib_frame = _to_qlib_dump_csv_frame(instrument, group)
                    qlib_frame.to_csv(qlib_csv_dir / f"{instrument}.csv", index=False, encoding="utf-8")

                    pickle_frame = _to_kronos_pickle_frame(group)
                    if len(pickle_frame) < min_rows:
                        skipped_groups += 1
                        continue

                    items.append(
                        (
                            instrument,
                            str(session),
                            pickle_frame.index.min(),
                            pickle_frame.index.max(),
                            pickle_frame,
                        )
                    )
                    written_groups += 1
                    written_rows += len(pickle_frame)

                table_reports.append(
                    {
                        "table": table,
                        "written_groups": written_groups,
                        "written_rows": written_rows,
                        "skipped_groups": skipped_groups,
                        "regularized_inserted_rows": table_grid_inserted_rows,
                        "mapping": {k: v for k, v in mapping.items() if k != "warnings"},
                    }
                )
            except Exception as exc:  # pragma: no cover - real DB diagnostics
                table_reports.append({"table": table, "error": str(exc)})
    finally:
        conn.close()

    if not items:
        raise ValueError(
            f"No STOM groups were exportable for min_rows={min_rows}. "
            "Lower lookback/predict windows or export more rows."
        )

    split_items = _split_items(items, config.train_ratio, config.val_ratio, config.test_ratio, split_by=config.split_by)
    split_sessions = _split_session_summary(split_items)
    split_counts: Dict[str, Dict[str, int]] = {}
    for split_name, split_rows in split_items.items():
        split_payload = {instrument: frame for instrument, _, _, _, frame in split_rows}
        with (processed_dir / f"{split_name}_data.pkl").open("wb") as f:
            pickle.dump(split_payload, f)
        split_counts[split_name] = {
            "groups": len(split_rows),
            "rows": int(sum(len(frame) for _, _, _, _, frame in split_rows)),
            "sessions": len(split_sessions.get(split_name, [])),
        }

    calendar = sorted({ts for _, _, _, _, frame in items for ts in frame.index})
    calendar_path = meta_dir / f"calendar_{config.freq}.txt"
    calendar_path.write_text("\n".join(ts.strftime("%Y-%m-%d %H:%M:%S") for ts in calendar) + "\n", encoding="utf-8")

    instruments_path = meta_dir / "instruments_all.txt"
    instruments_path.write_text(
        "\n".join(
            f"{instrument}\t{start.strftime('%Y-%m-%d %H:%M:%S')}\t{end.strftime('%Y-%m-%d %H:%M:%S')}"
            for instrument, _, start, end, _ in sorted(items, key=lambda item: item[0])
        )
        + "\n",
        encoding="utf-8",
    )

    dump_command = (
        "python scripts/dump_bin.py dump_all "
        f"--data_path {qlib_csv_dir.as_posix()} "
        f"--qlib_dir {(output_dir / 'qlib_bin').as_posix()} "
        "--date_field_name date --symbol_field_name symbol "
        f"--include_fields {','.join(QLIB_CSV_FIELDS)} "
        f"--freq {config.freq}"
    )
    (meta_dir / "qlib_dump_bin_command.txt").write_text(dump_command + "\n", encoding="utf-8")

    report = {
        "mode": "stom_to_qlib_export",
        "config": {**asdict(config), "effective_predict_window": predict_window},
        "min_rows_per_group": min_rows,
        "split_strategy": config.split_by,
        "output_dir": str(output_dir),
        "qlib_csv_dir": str(qlib_csv_dir),
        "processed_dataset_dir": str(processed_dir),
        "calendar_path": str(calendar_path),
        "instruments_path": str(instruments_path),
        "qlib_dump_bin_command": dump_command,
        "selected_table_count": len(config.tables) if config.tables else (config.max_tables or "all"),
        "exported_group_count": len(items),
        "exported_row_count": int(sum(len(frame) for _, _, _, _, frame in items)),
        "split_counts": split_counts,
        "split_sessions": split_sessions,
        "grid_summary": grid_summary,
        "warnings": sorted(set(warnings)),
        "tables": table_reports,
    }
    _write_json(output_dir / "stom_qlib_export_report.json", report)
    return report


def _pct_max_drawdown(equity: Sequence[float]) -> float:
    peak = -float("inf")
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return float(max_dd * 100.0)


def _load_prediction_latest(prediction_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(prediction_csv, dtype={"symbol": str, "session": str}, encoding="utf-8-sig")
    required = {"window_id", "symbol", "session", "asof_timestamp", "pred_return_window", "actual_return_window"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Prediction CSV missing required columns: {missing}")
    df["asof_timestamp"] = pd.to_datetime(df["asof_timestamp"], errors="coerce")
    sort_columns = ["window_id"]
    if "horizon_step" in df.columns:
        sort_columns.append("horizon_step")
    latest = df.sort_values(sort_columns).groupby("window_id").tail(1).copy()
    for column in ["pred_return_window", "actual_return_window", "direction_hit_window"]:
        if column in latest.columns:
            latest[column] = pd.to_numeric(latest[column], errors="coerce")
    latest = latest.dropna(subset=["asof_timestamp", "pred_return_window", "actual_return_window"])
    return latest


def run_score_backtest(
    prediction_csv: Path,
    output_dir: Path,
    top_k: int = 10,
    cost_bps: float = 0.0,
    slippage_bps: float = 0.0,
    score_column: str = "pred_return_window",
) -> Dict[str, Any]:
    """Run a deterministic Qlib-style Top-K backtest from prediction CSV scores."""

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    latest = _load_prediction_latest(prediction_csv)
    if score_column not in latest.columns:
        raise ValueError(f"score_column not found: {score_column}")

    output_dir.mkdir(parents=True, exist_ok=True)
    cost_pct = (cost_bps + slippage_bps) * 0.01
    rows: List[Dict[str, Any]] = []
    curve_rows: List[Dict[str, Any]] = []
    previous_symbols: set[str] = set()
    equity = 1.0
    equity_values = [equity]

    for timestamp, group in latest.groupby("asof_timestamp", sort=True):
        selected = group.sort_values(score_column, ascending=False).head(top_k).copy()
        if selected.empty:
            continue
        symbols = set(selected["symbol"].astype(str))
        gross = float(selected["actual_return_window"].mean())
        net = gross - cost_pct
        hit_rate = float((selected["actual_return_window"] > 0).mean())
        direction_hit = (
            float(selected["direction_hit_window"].mean())
            if "direction_hit_window" in selected.columns
            else float("nan")
        )
        turnover = 1.0
        if previous_symbols:
            turnover = 1.0 - len(symbols & previous_symbols) / max(len(symbols), 1)
        previous_symbols = symbols
        equity *= 1.0 + net / 100.0
        equity_values.append(equity)
        curve_rows.append(
            {
                "asof_timestamp": pd.Timestamp(timestamp).isoformat(),
                "gross_return_pct": gross,
                "net_return_pct": net,
                "hit_rate": hit_rate,
                "direction_hit": direction_hit,
                "turnover": turnover,
                "equity": equity,
            }
        )
        for rank, (_, row) in enumerate(selected.iterrows(), start=1):
            hit_value = row.get("direction_hit_window") if "direction_hit_window" in row else None
            direction_hit = None if pd.isna(hit_value) else int(hit_value)
            rows.append(
                {
                    "asof_timestamp": pd.Timestamp(timestamp).isoformat(),
                    "rank": rank,
                    "symbol": row.get("symbol"),
                    "session": row.get("session"),
                    "window_id": int(row.get("window_id")),
                    "score": float(row[score_column]),
                    "actual_return_pct": float(row["actual_return_window"]),
                    "net_return_pct": float(row["actual_return_window"] - cost_pct),
                    "direction_hit": direction_hit,
                }
            )

    if not curve_rows:
        raise ValueError("No backtest periods were generated.")

    curve = pd.DataFrame(curve_rows)
    trades = pd.DataFrame(rows)
    returns = curve["net_return_pct"].astype(float)
    sharpe = 0.0
    if len(returns) > 1 and returns.std(ddof=1) > 0:
        sharpe = float((returns.mean() / returns.std(ddof=1)) * math.sqrt(len(returns)))

    metrics = {
        "mode": "qlib_style_topk",
        "source_prediction_csv": str(prediction_csv),
        "top_k": top_k,
        "score_column": score_column,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "period_count": int(len(curve)),
        "trade_count": int(len(trades)),
        "avg_trades_per_period": float(len(trades) / len(curve)),
        "avg_gross_return_pct": float(curve["gross_return_pct"].mean()),
        "avg_net_return_pct": float(curve["net_return_pct"].mean()),
        "hit_rate": float((trades["actual_return_pct"] > 0).mean()),
        "direction_hit_rate": float(pd.to_numeric(trades["direction_hit"], errors="coerce").mean()),
        "avg_turnover": float(curve["turnover"].mean()),
        "cumulative_return_pct": float((equity - 1.0) * 100.0),
        "max_drawdown_pct": _pct_max_drawdown(equity_values),
        "sharpe_per_period": sharpe,
    }
    warnings: List[str] = []
    if metrics["avg_trades_per_period"] < top_k:
        warnings.append(
            "Average selected trades per period is below top_k. "
            "For true Qlib cross-sectional Top-K, generate predictions for multiple symbols at the same asof_timestamp."
        )
    payload = {
        "metrics": metrics,
        "warnings": warnings,
        "curve": curve_rows,
        "top_trades": rows[: min(len(rows), 500)],
    }
    stem = prediction_csv.stem
    json_path = output_dir / f"{stem}.qlib_topk{top_k}.json"
    curve_path = output_dir / f"{stem}.qlib_topk{top_k}.curve.csv"
    trades_path = output_dir / f"{stem}.qlib_topk{top_k}.trades.csv"
    _write_json(json_path, payload)
    curve.to_csv(curve_path, index=False, encoding="utf-8")
    trades.to_csv(trades_path, index=False, encoding="utf-8")
    return {
        **payload,
        "artifact_paths": {
            "json": str(json_path),
            "curve_csv": str(curve_path),
            "trades_csv": str(trades_path),
        },
    }


def _parse_tables(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="STOM -> Qlib/Kronos pilot pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Export STOM DB to Qlib dump-ready CSV and QlibDataset pickles")
    export.add_argument("--db", required=True)
    export.add_argument("--output-dir", required=True)
    export.add_argument("--max-tables", type=int, default=0)
    export.add_argument("--tables", default=None, help="Comma-separated table list")
    export.add_argument("--lookback-window", type=int, default=300)
    export.add_argument("--predict-window", type=int, default=60)
    export.add_argument("--price-mode", choices=["db_ohlc", "close_only"], default="close_only")
    export.add_argument("--time-start", default="090000")
    export.add_argument("--time-end", default="093000")
    export.add_argument("--session-start", default=None, help="Optional inclusive YYYYMMDD session lower bound.")
    export.add_argument("--session-end", default=None, help="Optional inclusive YYYYMMDD session upper bound.")
    export.add_argument("--max-rows-per-group", type=int, default=0)
    export.add_argument("--max-groups", type=int, default=0)
    export.add_argument("--freq", choices=sorted(SUPPORTED_FREQS), default="1s")
    export.add_argument(
        "--regularize-1s",
        action="store_true",
        help="Reindex 1-second exports to a strict 1-second grid. Prices forward-fill; missing volume/amount become 0.",
    )
    export.add_argument(
        "--split-by",
        choices=sorted(SUPPORTED_SPLIT_STRATEGIES),
        default="session",
        help="Split train/val/test by chronological session dates by default to reduce time-series leakage.",
    )
    export.add_argument(
        "--horizon-seconds",
        type=int,
        default=None,
        help="For 1-second exports, use this exact second horizon as the effective predict window.",
    )
    export.add_argument("--train-ratio", type=float, default=0.70)
    export.add_argument("--val-ratio", type=float, default=0.15)
    export.add_argument("--test-ratio", type=float, default=0.15)

    export_rl = sub.add_parser(
        "export-stom-rl",
        help="Export the 14 canonical STOM RL features for one symbol/time window (non-invasive, no full DB scan)",
    )
    export_rl.add_argument("--db", required=True)
    export_rl.add_argument("--output-dir", required=True)
    export_rl.add_argument("--table", required=True, help="Single symbol table name, e.g. 000020")
    export_rl.add_argument("--session", default=None, help="Optional YYYYMMDD session filter.")
    export_rl.add_argument("--time-start", default="090000")
    export_rl.add_argument("--time-end", default="093000")
    export_rl.add_argument("--max-rows", type=int, default=0, help="Cap rows after filtering. 0 means keep all.")
    export_rl.add_argument("--tick-size", type=float, default=1.0)

    backtest = sub.add_parser("score-backtest", help="Run Qlib-style Top-K backtest from Kronos prediction CSV")
    backtest.add_argument("--prediction-csv", required=True)
    backtest.add_argument("--output-dir", default="webui/qlib_backtests")
    backtest.add_argument("--top-k", type=int, default=10)
    backtest.add_argument("--cost-bps", type=float, default=0.0)
    backtest.add_argument("--slippage-bps", type=float, default=0.0)
    backtest.add_argument("--score-column", default="pred_return_window")

    env_check = sub.add_parser("qlib-env-check", help="Check optional pyqlib/dump_bin readiness")
    env_check.add_argument("--dump-bin-script", default=None)

    dump_bin = sub.add_parser("dump-bin", help="Build or execute Qlib dump_bin command from an export report")
    dump_bin.add_argument("--export-report", required=True)
    dump_bin.add_argument("--qlib-dir", default=None)
    dump_bin.add_argument("--dump-bin-script", default=None)
    dump_bin.add_argument("--freq", default=None)
    dump_bin.add_argument("--execute", action="store_true")

    provider = sub.add_parser("provider-smoke", help="Initialize pyqlib provider and read a calendar sample")
    provider.add_argument("--provider-uri", required=True)
    provider.add_argument("--region", choices=["cn", "us"], default="cn")
    provider.add_argument("--freq", default="day")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "export":
        report = export_stom_to_qlib(
            StomQlibExportConfig(
                db_path=args.db,
                output_dir=args.output_dir,
                max_tables=args.max_tables,
                tables=_parse_tables(args.tables),
                lookback_window=args.lookback_window,
                predict_window=args.predict_window,
                price_mode=args.price_mode,
                time_start=args.time_start,
                time_end=args.time_end,
                session_start=args.session_start,
                session_end=args.session_end,
                max_rows_per_group=args.max_rows_per_group,
                max_groups=args.max_groups,
                freq=args.freq,
                regularize_1s=args.regularize_1s,
                split_by=args.split_by,
                horizon_seconds=args.horizon_seconds,
                train_ratio=args.train_ratio,
                val_ratio=args.val_ratio,
                test_ratio=args.test_ratio,
            )
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "export-stom-rl":
        report = export_stom_rl_features(
            db_path=args.db,
            output_dir=args.output_dir,
            table=args.table,
            session=args.session,
            time_start=args.time_start,
            time_end=args.time_end,
            max_rows=args.max_rows,
            tick_size=args.tick_size,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "score-backtest":
        result = run_score_backtest(
            prediction_csv=Path(args.prediction_csv),
            output_dir=Path(args.output_dir),
            top_k=args.top_k,
            cost_bps=args.cost_bps,
            slippage_bps=args.slippage_bps,
            score_column=args.score_column,
        )
        print(
            json.dumps(
                result["metrics"]
                | {"warnings": result.get("warnings", []), "artifact_paths": result["artifact_paths"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "qlib-env-check":
        result = check_qlib_environment(Path(args.dump_bin_script) if args.dump_bin_script else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "dump-bin":
        result = run_dump_bin_from_report(
            export_report_path=Path(args.export_report),
            qlib_dir=Path(args.qlib_dir) if args.qlib_dir else None,
            dump_bin_script=Path(args.dump_bin_script) if args.dump_bin_script else None,
            execute=args.execute,
            freq=args.freq,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "provider-smoke":
        result = smoke_qlib_provider(Path(args.provider_uri), region=args.region, freq=args.freq)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
