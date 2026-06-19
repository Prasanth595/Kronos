"""Page 7.5 — multi-symbol 1s time-sync panel join (the core leakage gate).

This module aligns the 1-second canonical RL feature frames of *multiple*
symbols onto a single common ``timestamp`` grid.  It is the blocking
prerequisite for Page 9 (candidate CSV generation) because every downstream
decision/fill calculation assumes a point-in-time-correct panel.

Why a dedicated module (and why ``merge_asof`` only):

* The single most dangerous failure for an RL trading lab is **look-ahead
  leakage** — letting a value observed at a *future* second influence a row at
  time ``T``.  A naive ``reindex`` + forward/back-fill, an ``outer`` merge, or a
  ``ffill`` that crosses gaps can all silently pull a future observation
  backward.
* We therefore align every symbol with
  :func:`pandas.merge_asof` using ``direction="backward"`` *only*.  For grid
  time ``T`` a symbol contributes the most recent observation **at or before**
  ``T``.  A symbol with *no* observation at-or-before ``T`` (e.g. it lists later
  in the session, or is halted) yields ``NaN`` — never a future value.

  ``merge_asof(direction="backward")`` is the "as-of" join: stale-but-real is
  acceptable (the value genuinely existed at-or-before ``T``); future is not.
  The explicit limitation of this backward fill is that a long halt produces a
  *stale* value that persists until the next real observation; callers that want
  to treat long staleness as missing should pass ``tolerance`` (see below).

Output is **long-format** ``timestamp, symbol, <14 canonical features>`` to keep
memory bounded — a wide panel of 2400+ symbols would be mostly NaN.  Trading
halt / VI rows are excluded *before* the join and reported, so they can never
leak into the grid as a real observation.

Memory precondition (Page 7.5 P2-1): before any large/full-universe run, callers
must prove a single day-chunk fits the budget via
:func:`estimate_panel_memory` / :func:`assert_panel_memory_budget`:
``max_symbols * max_rows_per_group * bytes_per_row <= budget`` (default 2 GB).
The join itself is per-day-chunk; this module never performs a full DB scan.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finetune.qlib_stom_pipeline import (  # noqa: E402
    STOM_RL_CANONICAL_FEATURES,
    build_stom_rl_feature_frame,
    read_stom_table_rl_source,
    resample_stom_rl_source_frame,
)
from stom_tick_dataset import connect_readonly  # noqa: E402

# Long-format key columns prepended to the 14 canonical feature columns.
PANEL_KEY_COLUMNS: List[str] = ["timestamp", "symbol"]
PANEL_LONG_COLUMNS: List[str] = PANEL_KEY_COLUMNS + list(STOM_RL_CANONICAL_FEATURES)

# Default memory budget for the per-day-chunk precondition (2 GB).
DEFAULT_MEMORY_BUDGET_BYTES: int = 2 * 1024 * 1024 * 1024
# float64 (8 bytes) per canonical feature; one row carries the 14-feature vector.
BYTES_PER_FEATURE: int = 8


@dataclass
class SymbolFrame:
    """A single symbol's keyed canonical-feature frame ready for the panel.

    ``frame`` columns: ``timestamp`` (datetime64), ``symbol`` (str) and the 14
    :data:`STOM_RL_CANONICAL_FEATURES`.  Rows are sorted by ``timestamp`` and
    free of trading-halt / VI observations (those are reported separately).
    """

    symbol: str
    frame: pd.DataFrame
    excluded_halt_rows: int = 0
    raw_rows: int = 0
    session: Optional[str] = None


@dataclass
class PanelJoinReport:
    """Diagnostics for a panel join run (excluded rows, coverage, grid size)."""

    symbols: List[str] = field(default_factory=list)
    grid_size: int = 0
    grid_start: Optional[str] = None
    grid_end: Optional[str] = None
    per_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_excluded_halt_rows: int = 0
    memory: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "grid_size": int(self.grid_size),
            "grid_start": self.grid_start,
            "grid_end": self.grid_end,
            "per_symbol": self.per_symbol,
            "total_excluded_halt_rows": int(self.total_excluded_halt_rows),
            "memory": self.memory,
        }


# ---------------------------------------------------------------------------
# Memory precondition (P2-1)
# ---------------------------------------------------------------------------
def estimate_panel_memory(
    max_symbols: int,
    max_rows_per_group: int,
    bytes_per_row: int = BYTES_PER_FEATURE * len(STOM_RL_CANONICAL_FEATURES),
) -> Dict[str, Any]:
    """Estimate the worst-case bytes for one day-chunk of the long panel.

    The long format stores ``max_symbols * max_rows_per_group`` rows, each
    carrying the 14-feature float64 vector (``bytes_per_row``).  Key columns add
    a small constant overhead which we fold into a conservative 1.5x factor.
    """

    if max_symbols < 0 or max_rows_per_group < 0 or bytes_per_row < 0:
        raise ValueError("memory estimate inputs must be non-negative")
    feature_bytes = int(max_symbols) * int(max_rows_per_group) * int(bytes_per_row)
    estimated_bytes = int(feature_bytes * 1.5)  # key/index/object overhead headroom
    return {
        "max_symbols": int(max_symbols),
        "max_rows_per_group": int(max_rows_per_group),
        "bytes_per_row": int(bytes_per_row),
        "feature_bytes": feature_bytes,
        "estimated_bytes": estimated_bytes,
    }


def assert_panel_memory_budget(
    max_symbols: int,
    max_rows_per_group: int,
    budget_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES,
    bytes_per_row: int = BYTES_PER_FEATURE * len(STOM_RL_CANONICAL_FEATURES),
) -> Dict[str, Any]:
    """Raise unless ``max_symbols * max_rows_per_group * bytes_per_row <= budget``.

    Call this once before any large/full-universe run to prove a single day-chunk
    fits the configured budget (default 2 GB).
    """

    estimate = estimate_panel_memory(max_symbols, max_rows_per_group, bytes_per_row)
    estimate["budget_bytes"] = int(budget_bytes)
    estimate["within_budget"] = estimate["estimated_bytes"] <= int(budget_bytes)
    if not estimate["within_budget"]:
        raise MemoryError(
            "Panel day-chunk exceeds memory budget: "
            f"{estimate['estimated_bytes']} bytes estimated "
            f"({max_symbols} symbols x {max_rows_per_group} rows) "
            f"> budget {budget_bytes} bytes. Reduce max-symbols, shrink the time "
            "window (max-rows-per-group), or split the day into smaller chunks."
        )
    return estimate


# ---------------------------------------------------------------------------
# Halt / VI exclusion
# ---------------------------------------------------------------------------
def _exclude_halt_rows(
    keyed: pd.DataFrame,
    halt_mask: Optional[pd.Series] = None,
) -> Tuple[pd.DataFrame, int]:
    """Drop trading-halt / VI rows and return ``(clean_frame, excluded_count)``.

    A halt / VI second has no genuine tradable price.  We treat a row as
    halt-like when its ``close`` is missing or non-positive, or when the caller
    supplies an explicit boolean ``halt_mask`` (e.g. a VI flag from the source).
    Excluding *before* the as-of join guarantees a halted second can never become
    the "most recent observation at-or-before T" for the grid.
    """

    if keyed.empty:
        return keyed, 0
    close = pd.to_numeric(keyed.get("close"), errors="coerce")
    drop = close.isna() | (close <= 0.0)
    if halt_mask is not None:
        drop = drop | halt_mask.reindex(keyed.index, fill_value=False).astype(bool)
    excluded = int(drop.sum())
    clean = keyed.loc[~drop].reset_index(drop=True)
    return clean, excluded


def prepare_symbol_frame(
    keyed: pd.DataFrame,
    symbol: Optional[str] = None,
    halt_mask: Optional[pd.Series] = None,
) -> SymbolFrame:
    """Normalize one symbol's keyed canonical frame for the panel join.

    ``keyed`` must carry ``timestamp`` plus the 14 canonical features (and may
    carry ``symbol``/``session``).  The result is sorted by ``timestamp``,
    de-duplicated (keeping the last observation per second), halt-filtered, and
    reduced to long-panel columns.
    """

    raw_rows = int(len(keyed))
    if symbol is None:
        if "symbol" in keyed.columns and len(keyed) > 0:
            symbol = str(keyed["symbol"].iloc[0])
        else:
            raise ValueError("symbol must be provided when frame lacks a 'symbol' column")
    symbol = str(symbol)

    session: Optional[str] = None
    if "session" in keyed.columns and len(keyed) > 0:
        session = str(keyed["session"].iloc[0])

    work = keyed.copy()
    if "timestamp" not in work.columns:
        raise ValueError(f"symbol {symbol}: keyed frame is missing 'timestamp'")
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    work = work.dropna(subset=["timestamp"])

    missing_features = [c for c in STOM_RL_CANONICAL_FEATURES if c not in work.columns]
    if missing_features:
        raise ValueError(
            f"symbol {symbol}: keyed frame is missing canonical features: {missing_features}"
        )

    clean, excluded = _exclude_halt_rows(work, halt_mask=halt_mask)
    clean = clean.sort_values("timestamp", kind="mergesort")
    clean = clean.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    clean["symbol"] = symbol
    panel_frame = clean[["timestamp", "symbol", *STOM_RL_CANONICAL_FEATURES]].reset_index(drop=True)
    return SymbolFrame(
        symbol=symbol,
        frame=panel_frame,
        excluded_halt_rows=excluded,
        raw_rows=raw_rows,
        session=session,
    )


# ---------------------------------------------------------------------------
# Common-grid as-of join
# ---------------------------------------------------------------------------
def _build_common_grid(
    symbol_frames: Sequence[SymbolFrame],
    grid: Optional[pd.DatetimeIndex] = None,
) -> pd.DatetimeIndex:
    """Return the common 1s timestamp grid (union of observed seconds by default)."""

    if grid is not None:
        return pd.DatetimeIndex(pd.to_datetime(grid)).dropna().sort_values().unique()
    stamps: List[pd.Timestamp] = []
    for sf in symbol_frames:
        if not sf.frame.empty:
            stamps.append(sf.frame["timestamp"])
    if not stamps:
        return pd.DatetimeIndex([], dtype="datetime64[ns]")
    union = pd.concat(stamps, ignore_index=True)
    return pd.DatetimeIndex(union).dropna().sort_values().unique()


def join_symbol_frames(
    symbol_frames: Sequence[SymbolFrame],
    grid: Optional[pd.DatetimeIndex] = None,
    tolerance: Optional[pd.Timedelta] = None,
) -> Tuple[pd.DataFrame, PanelJoinReport]:
    """As-of (backward) join multiple symbol frames onto one common grid.

    For every grid timestamp ``T`` and every symbol, the panel carries that
    symbol's most recent observation **at or before** ``T`` (``merge_asof`` with
    ``direction="backward"``).  No observation at-or-before ``T`` -> ``NaN``.
    With ``tolerance`` set, an observation older than ``tolerance`` is also
    treated as missing (stale beyond the allowed staleness).

    Returns ``(long_panel, report)`` where ``long_panel`` has columns
    :data:`PANEL_LONG_COLUMNS` sorted by ``(timestamp, symbol)``.
    """

    grid_index = _build_common_grid(symbol_frames, grid=grid)
    report = PanelJoinReport(
        symbols=[sf.symbol for sf in symbol_frames],
        grid_size=int(len(grid_index)),
        grid_start=str(grid_index[0]) if len(grid_index) else None,
        grid_end=str(grid_index[-1]) if len(grid_index) else None,
    )

    if len(grid_index) == 0:
        empty = pd.DataFrame(columns=PANEL_LONG_COLUMNS)
        report.memory = estimate_panel_memory(len(symbol_frames), 0)
        return empty, report

    grid_df = pd.DataFrame({"timestamp": pd.DatetimeIndex(grid_index)})
    max_rows = 0
    parts: List[pd.DataFrame] = []
    for sf in symbol_frames:
        right = sf.frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        max_rows = max(max_rows, int(len(right)))
        feature_cols = list(STOM_RL_CANONICAL_FEATURES)
        if right.empty:
            # No observations at all -> entire column is NaN (never a future value).
            joined = grid_df.copy()
            joined["symbol"] = sf.symbol
            for col in feature_cols:
                joined[col] = np.nan
        else:
            # Backward as-of: each grid row gets the last obs at-or-before T.
            joined = pd.merge_asof(
                grid_df,
                right[["timestamp", *feature_cols]],
                on="timestamp",
                direction="backward",
                tolerance=tolerance,
            )
            joined["symbol"] = sf.symbol
        parts.append(joined[["timestamp", "symbol", *feature_cols]])

        non_null = int(joined[feature_cols[0]].notna().sum()) if feature_cols else 0
        report.per_symbol[sf.symbol] = {
            "observations": int(len(sf.frame)),
            "raw_rows": int(sf.raw_rows),
            "excluded_halt_rows": int(sf.excluded_halt_rows),
            "grid_rows_with_value": non_null,
            "grid_rows_nan": int(len(grid_index) - non_null),
            "session": sf.session,
        }
        report.total_excluded_halt_rows += int(sf.excluded_halt_rows)

    panel = pd.concat(parts, ignore_index=True)
    panel = panel.sort_values(["timestamp", "symbol"], kind="mergesort").reset_index(drop=True)
    panel = panel[PANEL_LONG_COLUMNS]

    report.memory = estimate_panel_memory(len(symbol_frames), max_rows)
    return panel, report


# ---------------------------------------------------------------------------
# DB-backed convenience (per-day-chunk; never a full scan)
# ---------------------------------------------------------------------------
def build_panel_from_db(
    db_path: Union[str, os.PathLike],
    tables: Sequence[str],
    session: Optional[str] = None,
    time_start: str = "090000",
    time_end: str = "093000",
    max_rows_per_group: int = 0,
    tick_size: float = 1.0,
    grid: Optional[pd.DatetimeIndex] = None,
    tolerance: Optional[pd.Timedelta] = None,
    memory_budget_bytes: int = DEFAULT_MEMORY_BUDGET_BYTES,
    freq: str = "1s",
) -> Tuple[pd.DataFrame, PanelJoinReport]:
    """Read several symbol tables for one day-window and as-of join them.

    This is a thin convenience wrapper over :func:`read_stom_table_rl_source` +
    :func:`build_stom_rl_feature_frame` (Page 7 per-symbol logic) and
    :func:`join_symbol_frames`.  It is bounded by the time window and optional
    ``max_rows_per_group`` so it never scans a whole table.  The memory budget is
    asserted up-front using the requested ``max_rows_per_group`` (a value of 0
    means "window-bounded"; supply a positive bound before a full-universe run).

    ``freq`` (default ``"1s"`` — the 1s path is byte-unchanged) selects the bar
    grid.  At ``"1min"`` the RL SOURCE frame is resampled by
    :func:`resample_stom_rl_source_frame` BEFORE :func:`build_stom_rl_feature_frame`
    so every derived feature (amount_delta, trailing means/slopes) recomputes on
    the 1-minute bars — this is THE live feed path where ``freq`` threads.
    """

    if max_rows_per_group and max_rows_per_group > 0:
        assert_panel_memory_budget(
            max_symbols=len(tables),
            max_rows_per_group=int(max_rows_per_group),
            budget_bytes=memory_budget_bytes,
        )

    conn = connect_readonly(db_path)
    symbol_frames: List[SymbolFrame] = []
    try:
        for table in tables:
            source_frame, _src_report = read_stom_table_rl_source(
                conn,
                table,
                session=session,
                time_start=time_start,
                time_end=time_end,
                max_rows=max_rows_per_group,
            )
            if source_frame.empty:
                symbol_frames.append(
                    SymbolFrame(
                        symbol=str(table),
                        frame=pd.DataFrame(columns=["timestamp", "symbol", *STOM_RL_CANONICAL_FEATURES]),
                        excluded_halt_rows=0,
                        raw_rows=0,
                        session=session,
                    )
                )
                continue
            # Resample the 18-col RL SOURCE frame BEFORE the feature builder so
            # derived features recompute on the requested bar grid (R1/R2).  At
            # freq="1s" this returns the frame unchanged (1s path untouched).
            source_frame = resample_stom_rl_source_frame(source_frame, freq=freq)
            # Story B1 SESSION bars are one row per (symbol, session): the causal
            # trend features must compute *across the per-symbol session series*
            # (group by symbol only), else each per-session group is a length-1
            # window and every trend feature collapses to a constant (which would
            # trip V-NONDEGEN).  1s/1min keep the default [symbol, session].
            trend_group_keys = ["symbol"] if freq == "session" else None
            features = build_stom_rl_feature_frame(
                source_frame, tick_size=tick_size, trend_group_keys=trend_group_keys
            )
            keyed = pd.concat(
                [
                    source_frame[["timestamp", "symbol", "session"]].reset_index(drop=True),
                    features.reset_index(drop=True),
                ],
                axis=1,
            )
            symbol_frames.append(prepare_symbol_frame(keyed))
    finally:
        conn.close()

    return join_symbol_frames(symbol_frames, grid=grid, tolerance=tolerance)
