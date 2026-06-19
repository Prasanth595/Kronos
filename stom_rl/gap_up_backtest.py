"""Opening gap-up momentum backtest (시초 갭상승 전략) on the real 1-second DB.

Strategy (user-specified, pre-registered BEFORE reading any result)
-------------------------------------------------------------------
* **Entry (시초 갭상승)** — for each recorded ``(symbol, session)`` in
  ``_database/stock_tick_back.db`` look at the FIRST bar of the session
  (the earliest row at or after ``09:00:00``).  If that bar's ``등락율``
  (percent change vs. previous close, stored in the DB) is ``>= 2.0`` enter
  LONG at that bar's ``현재가`` (current price).
* **Exit (first to trigger)** — walk the intra-session 1-second ``현재가``
  path FORWARD from the entry bar:
    - take-profit when price ``>= entry * (1 + tp_pct/100)``;
    - stop-loss when price ``<= entry * (1 - sl_pct/100)``;
    - else time-exit at ``09:25:00`` (시간청산) at that bar's price.
  The forward walk IS the legitimate trade execution — it only consumes
  prices at or after the entry second, so there is NO look-ahead at ENTRY
  (the entry decision uses only the first bar's 등락율).
* **Cost** — a configurable round-trip model
  (:func:`round_trip_cost_bps`):
  ``commission_bps_per_side*2 + transaction_tax_bps (SELL side only)
  + slippage_bps``.  The legacy flat 25 bp is the default total; a cost SWEEP
  over ``{0,5,10,15,18,25}`` bp is run to report the BREAKEVEN round-trip cost
  at which OOS net expectancy crosses zero (a property, not a tuned cell).
* **Entry filters (optional, pre-registered from STOM buy rules)** — on top of
  the 등락율>=2% gate, optionally require causal ENTRY-BAR demand signals:
  ``체결강도``(trade_strength) and 호가 ``bid_ask_imbalance``
  (매수총잔량/(매수+매도총잔량)).  Filters use only entry-bar values (<= entry
  second), so there is no look-ahead.  Definitions are pre-registered
  (:data:`ENTRY_FILTERS`), drawn from ``stom_rl/rules/buy_demand_pressure.json``
  / ``buy_widev1.json`` — NOT searched for the best threshold.

Honesty caveats (locked, see the doc)
-------------------------------------
* The TP/SL pair is SWEPT over a small grid (``TP x SL``); the full surface
  is reported and no single cell is cherry-picked as "the" answer.
* The cost sweep reports the BREAKEVEN cost (where OOS expectancy = 0), not a
  cherry-picked low-cost cell, and the entry filters are pre-registered (no
  threshold search).
* The universe is a TRIGGERED subset: the DB only recorded a session because
  it hit *some* STOM condition, so 등락율>=2% instances here are NOT a random
  sample of all 2%+ market gap-ups.  Results may not generalise.
* In-sample / out-of-sample split is by DATE (earlier sessions in-sample,
  later sessions out-of-sample) so an overfit TP/SL is exposed.

Bounded reads (NO full 28GB scan)
---------------------------------
Sessions are enumerated with the cheap per-table
``SELECT DISTINCT substr(index,1,8)`` query (:func:`enumerate_sessions`,
Story B1 pattern), then each ``(symbol, session)`` is read with a single
session-prefix-filtered, index-ordered query over the entry->09:25 window.
Each per-instance read touches one table's morning window only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from finetune_csv.stom_tick_dataset import (  # noqa: E402
    connect_readonly,
    get_table_columns,
    list_stock_tables,
)

# ---------------------------------------------------------------------------
# Locked pre-registration constants (DO NOT tune after seeing results).
# ---------------------------------------------------------------------------
ENTRY_CHANGE_RATE_THRESHOLD: float = 2.0  # 등락율 >= 2.0% at the first bar
TIME_EXIT_HHMMSS: str = "092500"  # 시간청산 cutoff (data ends ~0930)
SESSION_START_HHMMSS: str = "090000"
COST_BPS_ROUND_TRIP: float = 25.0  # entry + exit combined, basis points (legacy flat)

# Swept TP/SL grid (M = 16 combos).  Reported in full; no cherry-pick.
TP_GRID_PCT: Tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)
SL_GRID_PCT: Tuple[float, ...] = (1.0, 1.5, 2.0, 3.0)

# Cost SWEEP of round-trip levels (bps).  Used to locate the breakeven cost
# (OOS net expectancy = 0).  Includes the two labelled reference scenarios:
#   * Korean-domestic ~18 bp  (commission ~1.5 bp/side + transaction tax ~15 bp
#     on the SELL side only); see KOREAN_DOMESTIC_COST.
#   * International / low ~5 bp (commission ~2.5 bp/side, no transaction tax);
#     see INTERNATIONAL_LOW_COST.
COST_SWEEP_BPS: Tuple[float, ...] = (0.0, 5.0, 10.0, 15.0, 18.0, 25.0)

# Pre-registered entry filters (NOT threshold-searched).  Thresholds are the
# STOM canonical values (체결강도 >= 100 = "at par", 호가 imbalance >= 0.5 =
# "bid-side leaning") taken verbatim from buy_widev1.json / buy_demand_pressure
# .json — NOT tuned on this backtest's results.
TRADE_STRENGTH_THRESHOLD: float = 100.0  # 체결강도 >= 100 (STOM "at par")
IMBALANCE_THRESHOLD: float = 0.5  # 호가 매수총잔량/(매수+매도총잔량) >= 0.5

# DB column resolution (Korean names stored UTF-8; sqlite3 decodes by default).
_TIMESTAMP_CANDIDATES: Tuple[str, ...] = ("index", "timestamps", "timestamp")
_PRICE_CANDIDATES: Tuple[str, ...] = ("현재가", "종가", "close")
_CHANGE_RATE_CANDIDATES: Tuple[str, ...] = ("등락율",)
_TRADE_STRENGTH_CANDIDATES: Tuple[str, ...] = ("체결강도",)
_SEC_AMOUNT_CANDIDATES: Tuple[str, ...] = ("초당거래대금",)
_BID_QTY_CANDIDATES: Tuple[str, ...] = ("매수총잔량",)
_ASK_QTY_CANDIDATES: Tuple[str, ...] = ("매도총잔량",)

# Exit-reason labels.
EXIT_TP = "tp"
EXIT_SL = "sl"
EXIT_TIME = "time"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _resolve_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Realistic round-trip cost model (commission + sell-side tax + slippage).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RoundTripCost:
    """A realistic per-round-trip cost model (all components in basis points).

    A round trip is one BUY (entry) + one SELL (exit).  The total round-trip
    cost is::

        commission_bps_per_side * 2      (commission charged on BOTH sides)
        + transaction_tax_bps            (Korean 증권거래세 — SELL side ONLY)
        + slippage_bps                   (round-trip execution slippage)

    The transaction tax is applied ONCE (sell side only); buying incurs no
    transaction tax in the Korean market, hence it is not multiplied by two.
    """

    commission_bps_per_side: float = 0.0
    transaction_tax_bps: float = 0.0  # sell side only
    slippage_bps: float = 0.0

    def total_round_trip_bps(self) -> float:
        return round_trip_cost_bps(
            commission_bps_per_side=self.commission_bps_per_side,
            transaction_tax_bps=self.transaction_tax_bps,
            slippage_bps=self.slippage_bps,
        )


def round_trip_cost_bps(
    *,
    commission_bps_per_side: float = 0.0,
    transaction_tax_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> float:
    """Compute the total round-trip cost in basis points.

    ``commission_bps_per_side`` is charged on BOTH the buy and the sell, so it
    is doubled.  ``transaction_tax_bps`` (증권거래세) is charged on the SELL side
    ONLY, so it is added once.  ``slippage_bps`` is the round-trip slippage.
    """

    if (
        commission_bps_per_side < 0
        or transaction_tax_bps < 0
        or slippage_bps < 0
    ):
        raise ValueError("cost components must be non-negative")
    return (
        commission_bps_per_side * 2.0
        + transaction_tax_bps
        + slippage_bps
    )


# Two labelled reference scenarios (see COST_SWEEP_BPS docstring).
# Korean-domestic: commission ~1.5 bp/side + 증권거래세 ~15 bp (sell only)
#   -> 1.5*2 + 15 = 18 bp round trip.
KOREAN_DOMESTIC_COST = RoundTripCost(
    commission_bps_per_side=1.5, transaction_tax_bps=15.0, slippage_bps=0.0
)
# International / low: commission ~2.5 bp/side, no transaction tax
#   -> 2.5*2 + 0 = 5 bp round trip.
INTERNATIONAL_LOW_COST = RoundTripCost(
    commission_bps_per_side=2.5, transaction_tax_bps=0.0, slippage_bps=0.0
)


# ---------------------------------------------------------------------------
# Pre-registered causal entry filters (STOM buy-rule derived; NOT searched).
# ---------------------------------------------------------------------------
def compute_bid_ask_imbalance(
    bid_total_qty: Optional[float], ask_total_qty: Optional[float]
) -> Optional[float]:
    """호가 imbalance = 매수총잔량 / (매수총잔량 + 매도총잔량).

    Returns ``None`` when either side is missing or the book is empty (no
    denominator).  Range is ``[0, 1]``; ``>= 0.5`` means the book leans bid-side
    (more resting buy interest), the STOM 호가상승압력 intent.
    """

    if bid_total_qty is None or ask_total_qty is None:
        return None
    try:
        bid = float(bid_total_qty)
        ask = float(ask_total_qty)
    except (TypeError, ValueError):
        return None
    denom = bid + ask
    if denom <= 0:
        return None
    return bid / denom


@dataclass(frozen=True)
class EntryFilter:
    """A pre-registered causal entry filter (evaluated on the ENTRY BAR only)."""

    name: str
    require_trade_strength: bool = False
    require_imbalance: bool = False
    trade_strength_threshold: float = TRADE_STRENGTH_THRESHOLD
    imbalance_threshold: float = IMBALANCE_THRESHOLD


# Pre-registered filter set.  "none" = baseline (등락율>=2% only); F1/F2 are the
# STOM demand gates.  These are FIXED definitions (no per-result tuning).
ENTRY_FILTERS: Dict[str, EntryFilter] = {
    "none": EntryFilter(name="none"),
    # F1: 체결강도 >= 100 (STOM buy_widev1 / buy_demand_pressure "at par").
    "ts": EntryFilter(name="ts", require_trade_strength=True),
    # F2: 체결강도 >= 100 AND 호가 imbalance >= 0.5 (full buy_demand_pressure).
    "ts_imb": EntryFilter(
        name="ts_imb", require_trade_strength=True, require_imbalance=True
    ),
}


def passes_entry_filter(
    inst: "GapUpInstance", entry_filter: EntryFilter
) -> bool:
    """Return True if the instance's ENTRY-BAR signals satisfy the filter.

    Uses ONLY the entry-bar (<= entry second) ``trade_strength`` and
    ``bid_ask_imbalance`` already captured on the instance, so there is no
    look-ahead.  A required signal that is missing (``None``) FAILS the filter
    (we do not silently admit instances lacking the demand evidence).
    """

    if entry_filter.require_trade_strength:
        ts = inst.entry_trade_strength
        if ts is None or ts < entry_filter.trade_strength_threshold:
            return False
    if entry_filter.require_imbalance:
        imb = inst.entry_bid_ask_imbalance
        if imb is None or imb < entry_filter.imbalance_threshold:
            return False
    return True


def filter_instances(
    instances: Sequence["GapUpInstance"], entry_filter: EntryFilter
) -> List["GapUpInstance"]:
    """Apply a pre-registered entry filter, returning the surviving instances."""

    return [inst for inst in instances if passes_entry_filter(inst, entry_filter)]


# ---------------------------------------------------------------------------
# Pure trade-execution core (unit-tested on synthetic paths; no DB / no I/O).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TradeResult:
    """One resolved gap-up trade.

    ``net_return_pct`` is the round-trip-cost-adjusted percent return; the gross
    return is the raw exit/entry move.  ``exit_reason`` is one of
    :data:`EXIT_TP` / :data:`EXIT_SL` / :data:`EXIT_TIME`.
    """

    entry_price: float
    exit_price: float
    exit_reason: str
    hold_seconds: int
    gross_return_pct: float
    net_return_pct: float


_FILL_MODES: frozenset = frozenset({"idealized", "realized", "sl_gap_stress"})


def simulate_trade(
    prices: Sequence[float],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_bps: float = COST_BPS_ROUND_TRIP,
    seconds: Optional[Sequence[int]] = None,
    fill_mode: str = "idealized",
) -> TradeResult:
    """Walk a forward 1s price path from entry and resolve the exit.

    ``prices[0]`` is the entry (the first bar's price); subsequent elements are
    the forward path up to and including the time-exit bar (the caller bounds
    the path at 09:25:00).  The walk returns at the FIRST second whose price
    crosses TP or SL; if neither triggers it time-exits at the last price.

    A bar that crosses BOTH the TP and SL thresholds in the same second
    (a gap through the band) is resolved CONSERVATIVELY as a stop-loss — the
    pessimistic assumption for a long, since we cannot know intra-second order.

    ``net_return_pct`` subtracts the full round-trip ``cost_bps`` (entry+exit)
    from the gross move.  ``seconds`` (optional) supplies the elapsed-second of
    each path element so the reported ``hold_seconds`` reflects wall-clock time;
    when absent the index is used.

    ``fill_mode`` controls how the booked exit price is determined once a
    threshold is crossed — three modes are supported:

    * ``"idealized"`` (default): SL books at exactly ``sl_level``; TP books at
      exactly ``tp_level``.  This is the original behaviour and preserves all
      prior test results.
    * ``"realized"``: SL books at ``min(price, sl_level)`` — the actual bar
      price, which may gap *through* the level for a worse fill; TP books at
      ``max(price, tp_level)`` — the actual bar price, which may overshoot for
      a better fill.
    * ``"sl_gap_stress"`` (most pessimistic overall): SL books at
      ``min(price, sl_level)`` like ``"realized"`` (gap-through worst case);
      TP books at ``tp_level`` like ``"idealized"`` (conservative, no credit
      for overshoot).  Use this to stress-test whether the edge survives the
      combined worst-case scenario.
    """

    if fill_mode not in _FILL_MODES:
        raise ValueError(
            f"fill_mode must be one of {sorted(_FILL_MODES)!r}, got {fill_mode!r}"
        )
    if tp_pct <= 0 or sl_pct <= 0:
        raise ValueError("tp_pct and sl_pct must be positive")
    if not prices:
        raise ValueError("prices must contain at least the entry bar")
    entry = float(prices[0])
    if entry <= 0:
        raise ValueError("entry price must be positive")

    tp_level = entry * (1.0 + tp_pct / 100.0)
    sl_level = entry * (1.0 - sl_pct / 100.0)
    cost_pct = float(cost_bps) / 100.0  # 25 bps -> 0.25%

    def _elapsed(idx: int) -> int:
        if seconds is not None and idx < len(seconds):
            return int(seconds[idx]) - int(seconds[0])
        return int(idx)

    def _sl_fill(price: float) -> float:
        # idealized: book at the exact SL level (optimistic).
        # realized / sl_gap_stress: book at the actual crossing price (realistic
        # worst-case: gap-through fills at the bar price, not the level).
        if fill_mode == "idealized":
            return sl_level
        return min(price, sl_level)

    def _tp_fill(price: float) -> float:
        # realized: book at the actual crossing price (may be above tp_level on
        # gap-through — a better fill for the long).
        # idealized / sl_gap_stress: book at the exact TP level (conservative).
        if fill_mode == "realized":
            return max(price, tp_level)
        return tp_level

    exit_idx = len(prices) - 1
    exit_price = float(prices[-1])
    exit_reason = EXIT_TIME

    # Forward walk: start at the SECOND bar (index 1).  The entry bar itself
    # cannot also be the exit — the trade is opened on it.
    for idx in range(1, len(prices)):
        price = float(prices[idx])
        hit_sl = price <= sl_level
        hit_tp = price >= tp_level
        if hit_sl:  # conservative: SL wins a same-bar TP+SL straddle
            exit_idx, exit_price, exit_reason = idx, _sl_fill(price), EXIT_SL
            break
        if hit_tp:
            exit_idx, exit_price, exit_reason = idx, _tp_fill(price), EXIT_TP
            break

    gross = (exit_price / entry - 1.0) * 100.0
    net = gross - cost_pct
    return TradeResult(
        entry_price=entry,
        exit_price=float(exit_price),
        exit_reason=exit_reason,
        hold_seconds=_elapsed(exit_idx),
        gross_return_pct=float(gross),
        net_return_pct=float(net),
    )


def simulate_baseline(
    prices: Sequence[float],
    *,
    cost_bps: float = COST_BPS_ROUND_TRIP,
    seconds: Optional[Sequence[int]] = None,
) -> TradeResult:
    """Baseline: buy@open, hold to the time-exit bar, NO TP/SL.

    Exit is always the last price on the bounded path (09:25), so this measures
    "just ride the gap" net of the same round-trip cost.
    """

    if not prices:
        raise ValueError("prices must contain at least the entry bar")
    entry = float(prices[0])
    if entry <= 0:
        raise ValueError("entry price must be positive")
    exit_price = float(prices[-1])
    cost_pct = float(cost_bps) / 100.0
    gross = (exit_price / entry - 1.0) * 100.0
    net = gross - cost_pct
    last_idx = len(prices) - 1
    if seconds is not None and last_idx < len(seconds):
        hold = int(seconds[last_idx]) - int(seconds[0])
    else:
        hold = int(last_idx)
    return TradeResult(
        entry_price=entry,
        exit_price=exit_price,
        exit_reason=EXIT_TIME,
        hold_seconds=hold,
        gross_return_pct=float(gross),
        net_return_pct=float(net),
    )


# ---------------------------------------------------------------------------
# Per-instance DB read (bounded; session-prefix indexed; entry->09:25 window).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GapUpInstance:
    """A resolved gap-up entry candidate for one (symbol, session).

    ``entry_trade_strength`` (체결강도), ``entry_sec_amount`` (초당거래대금) and
    ``entry_bid_ask_imbalance`` are the CAUSAL entry-bar demand signals used by
    :func:`passes_entry_filter`; all are taken from the FIRST (entry) bar only,
    so they never look ahead.  Any may be ``None`` when the source column is
    absent or unreadable.
    """

    symbol: str
    session: str
    entry_change_rate: float
    entry_price: float
    prices: Tuple[float, ...]
    seconds: Tuple[int, ...]
    entry_trade_strength: Optional[float] = None
    entry_sec_amount: Optional[float] = None
    entry_bid_ask_imbalance: Optional[float] = None


def _hhmmss_of(ts: int) -> str:
    return str(int(ts))[8:14]


def _seconds_since_midnight(ts: int) -> int:
    s = str(int(ts))
    hh, mm, ss = int(s[8:10]), int(s[10:12]), int(s[12:14])
    return hh * 3600 + mm * 60 + ss


def read_gap_up_instance(
    conn: Any,
    table: str,
    session: str,
    *,
    timestamp_col: str,
    price_col: str,
    change_rate_col: str,
    trade_strength_col: Optional[str] = None,
    sec_amount_col: Optional[str] = None,
    bid_qty_col: Optional[str] = None,
    ask_qty_col: Optional[str] = None,
    entry_threshold: float = ENTRY_CHANGE_RATE_THRESHOLD,
    session_start: str = SESSION_START_HHMMSS,
    time_exit: str = TIME_EXIT_HHMMSS,
) -> Optional[GapUpInstance]:
    """Read one (symbol, session) window and return a gap-up instance or None.

    A single session-prefix-filtered, index-ordered query pulls the rows from
    ``session_start`` to ``time_exit`` (inclusive).  The entry is the FIRST row;
    if its 등락율 < ``entry_threshold`` (or price is non-positive) the session is
    skipped (returns None).  The forward path is every row from entry to the
    time-exit cutoff.  This touches one table's morning window only.

    When the optional demand columns (``trade_strength_col`` = 체결강도,
    ``sec_amount_col`` = 초당거래대금, ``bid_qty_col``/``ask_qty_col`` =
    매수/매도총잔량) are supplied they are read from the ENTRY bar ONLY and stored
    on the instance for the causal entry filters (no look-ahead).
    """

    if len(session) != 8 or not session.isdigit():
        raise ValueError(f"session must be YYYYMMDD, got: {session}")
    qt = _quote_ident(table)
    ts_q = _quote_ident(timestamp_col)
    px_q = _quote_ident(price_col)
    cr_q = _quote_ident(change_rate_col)
    # Optional demand columns appended AFTER the core three (entry-bar only).
    extra_cols = [trade_strength_col, sec_amount_col, bid_qty_col, ask_qty_col]
    select_extra = "".join(
        f", {_quote_ident(c)}" if c else ", NULL" for c in extra_cols
    )
    start_full = int(session + session_start)
    end_full = int(session + time_exit)
    query = (
        f"SELECT {ts_q}, {px_q}, {cr_q}{select_extra} FROM {qt} "
        f"WHERE {ts_q} >= ? AND {ts_q} <= ? "
        f"ORDER BY {ts_q}"
    )
    rows = conn.execute(query, (start_full, end_full)).fetchall()
    if not rows:
        return None

    # Entry = first bar of the session window.
    entry_row = rows[0]
    entry_px, entry_cr = entry_row[1], entry_row[2]
    if entry_cr is None or entry_px is None:
        return None
    try:
        entry_cr = float(entry_cr)
        entry_px = float(entry_px)
    except (TypeError, ValueError):
        return None
    if entry_px <= 0 or entry_cr < float(entry_threshold):
        return None

    # CAUSAL entry-bar demand signals (entry row only; never look ahead).
    def _opt_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    entry_trade_strength = _opt_float(entry_row[3])
    entry_sec_amount = _opt_float(entry_row[4])
    entry_bid_qty = _opt_float(entry_row[5])
    entry_ask_qty = _opt_float(entry_row[6])
    entry_imbalance = compute_bid_ask_imbalance(entry_bid_qty, entry_ask_qty)

    prices: List[float] = []
    secs: List[int] = []
    for row in rows:
        ts, px = row[0], row[1]
        if px is None:
            continue
        try:
            p = float(px)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        prices.append(p)
        secs.append(_seconds_since_midnight(int(ts)))
    if len(prices) < 1:
        return None

    return GapUpInstance(
        symbol=str(table),
        session=str(session),
        entry_change_rate=entry_cr,
        entry_price=prices[0],
        prices=tuple(prices),
        seconds=tuple(secs),
        entry_trade_strength=entry_trade_strength,
        entry_sec_amount=entry_sec_amount,
        entry_bid_ask_imbalance=entry_imbalance,
    )


# ---------------------------------------------------------------------------
# Aggregation over a set of resolved trades.
# ---------------------------------------------------------------------------
def aggregate_trades(trades: Sequence[TradeResult]) -> Dict[str, Any]:
    """Summarise a set of resolved trades into honest aggregate metrics."""

    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0,
            "win_rate": None,
            "mean_net_return_pct": None,
            "total_net_return_pct": 0.0,
            "expectancy_pct": None,
            "mean_gross_return_pct": None,
            "avg_hold_seconds": None,
            "exit_mix": {EXIT_TP: 0.0, EXIT_SL: 0.0, EXIT_TIME: 0.0},
        }
    nets = [t.net_return_pct for t in trades]
    grosses = [t.gross_return_pct for t in trades]
    holds = [t.hold_seconds for t in trades]
    wins = sum(1 for v in nets if v > 0.0)
    counts = {EXIT_TP: 0, EXIT_SL: 0, EXIT_TIME: 0}
    for t in trades:
        counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
    total_net = float(sum(nets))
    return {
        "n_trades": n,
        "win_rate": wins / n,
        "mean_net_return_pct": total_net / n,
        "total_net_return_pct": total_net,
        "expectancy_pct": total_net / n,  # per-trade expectancy net of cost
        "mean_gross_return_pct": float(sum(grosses)) / n,
        "avg_hold_seconds": float(sum(holds)) / n,
        "exit_mix": {k: counts[k] / n for k in (EXIT_TP, EXIT_SL, EXIT_TIME)},
    }


def split_instances_by_date(
    instances: Sequence[GapUpInstance],
    in_sample_fraction: float = 0.7,
) -> Tuple[List[GapUpInstance], List[GapUpInstance], Optional[str]]:
    """Split instances by SESSION DATE into in-sample (earlier) / OOS (later).

    The split boundary is the date at the ``in_sample_fraction`` quantile of the
    sorted distinct session dates.  All instances on a date <= boundary are
    in-sample; later dates are out-of-sample.  Returns
    ``(in_sample, out_of_sample, boundary_date)``.
    """

    if not instances:
        return [], [], None
    dates = sorted({inst.session for inst in instances})
    if len(dates) == 1:
        return list(instances), [], dates[0]
    cut_index = max(0, min(len(dates) - 1, int(round(len(dates) * in_sample_fraction)) - 1))
    boundary = dates[cut_index]
    in_sample = [inst for inst in instances if inst.session <= boundary]
    out_of_sample = [inst for inst in instances if inst.session > boundary]
    return in_sample, out_of_sample, boundary


# ---------------------------------------------------------------------------
# Cost sweep + breakeven (the breakeven is a PROPERTY, not a tuned cell).
# ---------------------------------------------------------------------------
def expectancy_at_cost(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_bps: float,
    fill_mode: str = "idealized",
) -> Optional[float]:
    """Net per-trade expectancy (%) for one TP/SL at one round-trip cost.

    Returns ``None`` for an empty instance set.  Because cost enters the net
    return purely additively (``net = gross - cost%``), expectancy is exactly
    ``gross_expectancy - cost_bps/100`` and STRICTLY DECREASES as cost rises —
    this monotonicity is what makes the breakeven well-defined.

    ``fill_mode`` is forwarded to :func:`simulate_trade`; see that function's
    docstring for the three supported modes.
    """

    if not instances:
        return None
    trades = [
        simulate_trade(
            inst.prices,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            cost_bps=cost_bps,
            seconds=inst.seconds,
            fill_mode=fill_mode,
        )
        for inst in instances
    ]
    return aggregate_trades(trades)["expectancy_pct"]


def breakeven_round_trip_bps(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    fill_mode: str = "idealized",
) -> Optional[float]:
    """Round-trip cost (bps) at which net expectancy crosses 0 for this TP/SL.

    Net expectancy = ``gross_expectancy_pct - cost_bps/100``; it is 0 exactly
    when ``cost_bps = gross_expectancy_pct * 100``.  A NEGATIVE result means even
    a zero-cost trade loses (gross edge < 0) — the strategy is unprofitable at
    ANY cost.  A POSITIVE result is the maximum tolerable round-trip cost.
    Returns ``None`` for an empty set.

    ``fill_mode`` is forwarded to :func:`simulate_trade`.
    """

    gross = expectancy_at_cost(
        instances, tp_pct=tp_pct, sl_pct=sl_pct, cost_bps=0.0, fill_mode=fill_mode
    )
    if gross is None:
        return None
    return gross * 100.0  # %/trade -> bps


def cost_sweep_table(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_levels: Sequence[float] = COST_SWEEP_BPS,
    fill_mode: str = "idealized",
) -> List[Dict[str, Any]]:
    """OOS-honest cost sweep: net expectancy at each round-trip cost level.

    ``fill_mode`` is forwarded to :func:`simulate_trade`.
    """

    return [
        {
            "cost_bps": float(c),
            "expectancy_pct": expectancy_at_cost(
                instances,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                cost_bps=float(c),
                fill_mode=fill_mode,
            ),
        }
        for c in cost_levels
    ]


# ---------------------------------------------------------------------------
# Regime-robustness analysis modes (per-year, multi-boundary, slippage).
#
# These answer "is the OOS-positive filtered gap-up edge regime-robust or a
# recent-bull artifact, and does it survive realistic slippage?".  All three
# reuse the SAME pure trade-execution core (:func:`simulate_trade`) and the
# SAME additive cost model, so a positive result is comparable to the prior
# cost-sweep run.  No new edge is "discovered" — these only re-slice the
# existing instances by calendar year / split boundary / total cost level.
# ---------------------------------------------------------------------------
# Slippage levels (bps) ADDED to the round-trip commission+tax cost.  Execution
# at a gap-up open is not free; this stresses the edge against that reality.
SLIPPAGE_SWEEP_BPS: Tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)
# Realistic Korean-domestic base cost (commission+tax) the slippage is added to.
REALISTIC_COST_BPS: float = 18.0


def year_of(session: str) -> str:
    """Calendar year (YYYY) of a YYYYMMDD session string.

    Raises ``ValueError`` for a malformed session so a bad date can never be
    silently bucketed into the wrong year.
    """

    s = str(session)
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"session must be YYYYMMDD, got: {session!r}")
    return s[:4]


def split_instances_by_year(
    instances: Sequence[GapUpInstance],
) -> Dict[str, List[GapUpInstance]]:
    """Bucket instances by their session's calendar year (YYYY).

    Returns an ordered dict (ascending year) so a strategy that is positive
    only in the latest years is visible as a recent-regime artifact rather than
    a robust edge.
    """

    buckets: Dict[str, List[GapUpInstance]] = {}
    for inst in instances:
        buckets.setdefault(year_of(inst.session), []).append(inst)
    return {year: buckets[year] for year in sorted(buckets)}


def per_year_expectancy(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_bps: float,
    fill_mode: str = "idealized",
) -> List[Dict[str, Any]]:
    """Net per-trade expectancy + N + win-rate for EACH calendar year.

    A signal positive only in recent years (e.g. 2025-2026) is a regime
    artifact; one positive across all years is robust.  Cost enters additively
    so each year's expectancy is that year's gross edge minus ``cost_bps/100``.

    ``fill_mode`` is forwarded to :func:`simulate_trade`.
    """

    rows: List[Dict[str, Any]] = []
    for year, year_insts in split_instances_by_year(instances).items():
        trades = [
            simulate_trade(
                inst.prices,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                cost_bps=cost_bps,
                seconds=inst.seconds,
                fill_mode=fill_mode,
            )
            for inst in year_insts
        ]
        agg = aggregate_trades(trades)
        rows.append(
            {
                "year": year,
                "n_trades": agg["n_trades"],
                "mean_net_return_pct": agg["mean_net_return_pct"],
                "win_rate": agg["win_rate"],
            }
        )
    return rows


def multi_boundary_oos(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_bps: float,
    fractions: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
    fill_mode: str = "idealized",
) -> List[Dict[str, Any]]:
    """Sweep the IS/OOS split boundary; report OOS expectancy at each.

    Instead of one favourable holdout date, this walks the boundary across the
    sorted distinct session dates (expanding in-sample window).  If the OOS
    expectancy stays positive as the boundary moves the edge is boundary-robust;
    if it is positive only for one boundary it is fragile.  Each row reports the
    boundary date, the IS/OOS instance counts, and the IS & OOS expectancy.

    ``fill_mode`` is forwarded to :func:`simulate_trade`.
    """

    rows: List[Dict[str, Any]] = []
    for frac in fractions:
        in_sample, out_sample, boundary = split_instances_by_date(
            instances, in_sample_fraction=float(frac)
        )
        rows.append(
            {
                "in_sample_fraction": float(frac),
                "boundary_date": boundary,
                "n_in_sample": len(in_sample),
                "n_out_of_sample": len(out_sample),
                "expectancy_in_sample": expectancy_at_cost(
                    in_sample,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    fill_mode=fill_mode,
                ),
                "expectancy_out_of_sample": expectancy_at_cost(
                    out_sample,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    fill_mode=fill_mode,
                ),
            }
        )
    return rows


def slippage_sensitivity(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    base_cost_bps: float = REALISTIC_COST_BPS,
    slippage_levels: Sequence[float] = SLIPPAGE_SWEEP_BPS,
    fill_mode: str = "idealized",
) -> List[Dict[str, Any]]:
    """Net expectancy at ``base_cost_bps + slippage`` for each slippage level.

    Slippage adds to the round-trip cost (verified by :func:`round_trip_cost_bps`
    composing commission+tax+slippage).  At each level the TOTAL cost is
    ``base_cost_bps + slippage_bps`` and the expectancy is computed with that
    total — so a filter whose breakeven exceeds base+slippage survives, one
    whose breakeven sits below it dies.  Returns one row per slippage level with
    the total cost and the resulting net expectancy.

    ``fill_mode`` is forwarded to :func:`simulate_trade`.
    """

    rows: List[Dict[str, Any]] = []
    for slip in slippage_levels:
        total_cost = round_trip_cost_bps(
            commission_bps_per_side=0.0,
            transaction_tax_bps=float(base_cost_bps),
            slippage_bps=float(slip),
        )
        rows.append(
            {
                "slippage_bps": float(slip),
                "base_cost_bps": float(base_cost_bps),
                "total_cost_bps": total_cost,
                "expectancy_pct": expectancy_at_cost(
                    instances,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=total_cost,
                    fill_mode=fill_mode,
                ),
            }
        )
    return rows


def compute_regime_analysis(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float,
    sl_pct: float,
    cost_bps: float = REALISTIC_COST_BPS,
    boundary_fractions: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
    slippage_levels: Sequence[float] = SLIPPAGE_SWEEP_BPS,
    fill_mode: str = "idealized",
) -> List[Dict[str, Any]]:
    """Per-filter regime robustness bundle (per-year + multi-boundary + slip).

    For EACH pre-registered entry filter, computes (a) the per-calendar-year
    expectancy at the realistic ``cost_bps``, (b) the OOS expectancy as the
    IS/OOS boundary is swept, and (c) the net expectancy as slippage is added to
    that cost.  This is the decisive regime-robustness + slippage-survivability
    evidence; it re-slices the SAME filtered instances, discovering no new edge.

    ``fill_mode`` is forwarded to :func:`simulate_trade` via all sub-analyses.
    """

    out: List[Dict[str, Any]] = []
    for fname, efilter in ENTRY_FILTERS.items():
        kept = filter_instances(instances, efilter)
        out.append(
            {
                "filter": fname,
                "primary_tp_pct": tp_pct,
                "primary_sl_pct": sl_pct,
                "cost_bps": float(cost_bps),
                "n_all": len(kept),
                "per_year": per_year_expectancy(
                    kept,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    fill_mode=fill_mode,
                ),
                "multi_boundary": multi_boundary_oos(
                    kept,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    fractions=boundary_fractions,
                    fill_mode=fill_mode,
                ),
                "slippage": slippage_sensitivity(
                    kept,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    base_cost_bps=cost_bps,
                    slippage_levels=slippage_levels,
                    fill_mode=fill_mode,
                ),
            }
        )
    return out


# ---------------------------------------------------------------------------
# DB-backed full backtest runner (bounded enumeration + per-instance reads).
# ---------------------------------------------------------------------------
@dataclass
class GapUpBacktestConfig:
    db_path: str
    max_symbols: int = 0  # 0 = all tables (full universe)
    in_sample_fraction: float = 0.7
    cost_bps: float = COST_BPS_ROUND_TRIP
    entry_threshold: float = ENTRY_CHANGE_RATE_THRESHOLD
    tp_grid: Tuple[float, ...] = TP_GRID_PCT
    sl_grid: Tuple[float, ...] = SL_GRID_PCT
    # Cost-sweep + filter analysis (the prior best cell is the PRIMARY TP/SL).
    cost_sweep_bps: Tuple[float, ...] = COST_SWEEP_BPS
    primary_tp_pct: float = 5.0  # prior "best OOS" cell (TP5/SL1), reported only
    primary_sl_pct: float = 1.0
    artifacts_dir: Optional[str] = None
    # Regime-robustness analysis (per-year / multi-boundary / slippage) at the
    # realistic cost; off by default so the existing cost-sweep run is unchanged.
    regime_analysis: bool = False
    regime_cost_bps: float = REALISTIC_COST_BPS
    boundary_fractions: Tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
    slippage_levels: Tuple[float, ...] = SLIPPAGE_SWEEP_BPS
    # TP/SL fill model: "idealized" preserves original behavior (exact levels);
    # "realized" uses actual crossing price; "sl_gap_stress" is the most
    # pessimistic (gap-through SL + conservative TP).  Default unchanged.
    fill_mode: str = "idealized"


@dataclass
class GapUpBacktestResult:
    instances: List[GapUpInstance] = field(default_factory=list)
    n_symbols: int = 0
    n_sessions: int = 0
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    boundary_date: Optional[str] = None
    grid: List[Dict[str, Any]] = field(default_factory=list)
    baseline: Dict[str, Any] = field(default_factory=dict)
    # Cost-sweep x filter analysis (keyed by filter name "none"/"ts"/"ts_imb").
    filter_analysis: List[Dict[str, Any]] = field(default_factory=list)
    # Regime-robustness analysis per filter (per-year / multi-boundary / slip).
    regime_analysis: List[Dict[str, Any]] = field(default_factory=list)


def collect_gap_up_instances(
    config: GapUpBacktestConfig,
) -> List[GapUpInstance]:
    """Enumerate tables, read each table's sessions, collect gap-up instances.

    Reads are bounded: one session-prefix-indexed morning-window query per
    (symbol, session).  Never materialises a full table.
    """

    conn = connect_readonly(config.db_path)
    instances: List[GapUpInstance] = []
    try:
        tables = list_stock_tables(
            conn, max_tables=config.max_symbols if config.max_symbols > 0 else None
        )
        for table in tables:
            columns = get_table_columns(conn, table)
            ts_col = _resolve_column(columns, _TIMESTAMP_CANDIDATES)
            px_col = _resolve_column(columns, _PRICE_CANDIDATES)
            cr_col = _resolve_column(columns, _CHANGE_RATE_CANDIDATES)
            if not ts_col or not px_col or not cr_col:
                continue  # table lacks the required columns; skip honestly
            # Optional causal demand columns (None when absent -> filter NULLs).
            ts_strength_col = _resolve_column(columns, _TRADE_STRENGTH_CANDIDATES)
            sec_amount_col = _resolve_column(columns, _SEC_AMOUNT_CANDIDATES)
            bid_qty_col = _resolve_column(columns, _BID_QTY_CANDIDATES)
            ask_qty_col = _resolve_column(columns, _ASK_QTY_CANDIDATES)
            qt = _quote_ident(table)
            ts_q = _quote_ident(ts_col)
            date_query = f"SELECT DISTINCT substr(CAST({ts_q} AS TEXT), 1, 8) FROM {qt}"
            session_dates = [
                str(row[0])
                for row in conn.execute(date_query).fetchall()
                if row[0] is not None and len(str(row[0])) == 8 and str(row[0]).isdigit()
            ]
            for session in sorted(session_dates):
                inst = read_gap_up_instance(
                    conn,
                    table,
                    session,
                    timestamp_col=ts_col,
                    price_col=px_col,
                    change_rate_col=cr_col,
                    trade_strength_col=ts_strength_col,
                    sec_amount_col=sec_amount_col,
                    bid_qty_col=bid_qty_col,
                    ask_qty_col=ask_qty_col,
                    entry_threshold=config.entry_threshold,
                )
                if inst is not None:
                    instances.append(inst)
    finally:
        conn.close()
    return instances


def run_gap_up_backtest(config: GapUpBacktestConfig) -> GapUpBacktestResult:
    """Run the full pre-registered gap-up backtest and return the result.

    Computes the per-TP/SL-combo metrics on BOTH the in-sample and out-of-sample
    split, plus the no-TP/SL baseline on each split.  No cell is selected as
    "the" answer here — the caller renders the full surface.
    """

    instances = collect_gap_up_instances(config)
    result = GapUpBacktestResult(instances=instances)
    if not instances:
        return result

    result.n_symbols = len({inst.symbol for inst in instances})
    sessions = {inst.session for inst in instances}
    result.n_sessions = len({(inst.symbol, inst.session) for inst in instances})
    result.date_min = min(sessions)
    result.date_max = max(sessions)

    in_sample, out_sample, boundary = split_instances_by_date(
        instances, in_sample_fraction=config.in_sample_fraction
    )
    result.boundary_date = boundary

    def _eval(insts: Sequence[GapUpInstance], tp: float, sl: float) -> Dict[str, Any]:
        trades = [
            simulate_trade(
                inst.prices,
                tp_pct=tp,
                sl_pct=sl,
                cost_bps=config.cost_bps,
                seconds=inst.seconds,
                fill_mode=config.fill_mode,
            )
            for inst in insts
        ]
        return aggregate_trades(trades)

    def _baseline(insts: Sequence[GapUpInstance]) -> Dict[str, Any]:
        trades = [
            simulate_baseline(inst.prices, cost_bps=config.cost_bps, seconds=inst.seconds)
            for inst in insts
        ]
        return aggregate_trades(trades)

    grid: List[Dict[str, Any]] = []
    for tp in config.tp_grid:
        for sl in config.sl_grid:
            grid.append(
                {
                    "tp_pct": tp,
                    "sl_pct": sl,
                    "in_sample": _eval(in_sample, tp, sl),
                    "out_of_sample": _eval(out_sample, tp, sl),
                    "all": _eval(instances, tp, sl),
                }
            )
    result.grid = grid
    result.baseline = {
        "in_sample": _baseline(in_sample),
        "out_of_sample": _baseline(out_sample),
        "all": _baseline(instances),
    }

    # ---- Cost-sweep x entry-filter analysis (PRIMARY TP/SL, OOS-honest) ----
    # For each pre-registered filter, report: surviving N (IS/OOS), the
    # breakeven round-trip cost (IS & OOS), and the net expectancy at every
    # swept cost level (IS & OOS).  The breakeven is a PROPERTY (gross edge x
    # 100), so reporting it across filters is not cherry-picking.
    tp_p, sl_p = config.primary_tp_pct, config.primary_sl_pct
    filter_analysis: List[Dict[str, Any]] = []
    for fname, efilter in ENTRY_FILTERS.items():
        is_f = filter_instances(in_sample, efilter)
        oos_f = filter_instances(out_sample, efilter)
        all_f = filter_instances(instances, efilter)
        filter_analysis.append(
            {
                "filter": fname,
                "n_in_sample": len(is_f),
                "n_out_of_sample": len(oos_f),
                "n_all": len(all_f),
                "primary_tp_pct": tp_p,
                "primary_sl_pct": sl_p,
                "breakeven_bps_in_sample": breakeven_round_trip_bps(
                    is_f, tp_pct=tp_p, sl_pct=sl_p, fill_mode=config.fill_mode
                ),
                "breakeven_bps_out_of_sample": breakeven_round_trip_bps(
                    oos_f, tp_pct=tp_p, sl_pct=sl_p, fill_mode=config.fill_mode
                ),
                "sweep_in_sample": cost_sweep_table(
                    is_f,
                    tp_pct=tp_p,
                    sl_pct=sl_p,
                    cost_levels=config.cost_sweep_bps,
                    fill_mode=config.fill_mode,
                ),
                "sweep_out_of_sample": cost_sweep_table(
                    oos_f,
                    tp_pct=tp_p,
                    sl_pct=sl_p,
                    cost_levels=config.cost_sweep_bps,
                    fill_mode=config.fill_mode,
                ),
            }
        )
    result.filter_analysis = filter_analysis

    # ---- Regime-robustness analysis (per-year / multi-boundary / slippage) ----
    if config.regime_analysis:
        result.regime_analysis = compute_regime_analysis(
            instances,
            tp_pct=tp_p,
            sl_pct=sl_p,
            cost_bps=config.regime_cost_bps,
            boundary_fractions=config.boundary_fractions,
            slippage_levels=config.slippage_levels,
            fill_mode=config.fill_mode,
        )

    if config.artifacts_dir:
        _write_artifacts(config, result, in_sample, out_sample)

    return result


def _write_artifacts(
    config: GapUpBacktestConfig,
    result: GapUpBacktestResult,
    in_sample: Sequence[GapUpInstance],
    out_sample: Sequence[GapUpInstance],
) -> None:
    """Write per-instance trades (gitignored) for audit."""

    out_dir = Path(config.artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    split_label = {id(inst): "in_sample" for inst in in_sample}
    split_label.update({id(inst): "out_of_sample" for inst in out_sample})

    rows: List[Dict[str, Any]] = []
    for inst in result.instances:
        rec: Dict[str, Any] = {
            "symbol": inst.symbol,
            "session": inst.session,
            "split": split_label.get(id(inst), "unknown"),
            "entry_change_rate": inst.entry_change_rate,
            "entry_price": inst.entry_price,
            "entry_trade_strength": inst.entry_trade_strength,
            "entry_sec_amount": inst.entry_sec_amount,
            "entry_bid_ask_imbalance": (
                round(inst.entry_bid_ask_imbalance, 6)
                if inst.entry_bid_ask_imbalance is not None
                else None
            ),
            "pass_ts": passes_entry_filter(inst, ENTRY_FILTERS["ts"]),
            "pass_ts_imb": passes_entry_filter(inst, ENTRY_FILTERS["ts_imb"]),
            "n_path_bars": len(inst.prices),
        }
        for tp in config.tp_grid:
            for sl in config.sl_grid:
                tr = simulate_trade(
                    inst.prices,
                    tp_pct=tp,
                    sl_pct=sl,
                    cost_bps=config.cost_bps,
                    seconds=inst.seconds,
                    fill_mode=config.fill_mode,
                )
                key = f"tp{tp:g}_sl{sl:g}"
                rec[f"{key}_reason"] = tr.exit_reason
                rec[f"{key}_net_pct"] = round(tr.net_return_pct, 6)
        base = simulate_baseline(inst.prices, cost_bps=config.cost_bps, seconds=inst.seconds)
        rec["baseline_net_pct"] = round(base.net_return_pct, 6)
        rec["baseline_hold_seconds"] = base.hold_seconds
        rows.append(rec)

    (out_dir / "instances.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "n_instances": len(result.instances),
        "n_symbols": result.n_symbols,
        "n_sessions": result.n_sessions,
        "date_min": result.date_min,
        "date_max": result.date_max,
        "boundary_date": result.boundary_date,
        "cost_bps": config.cost_bps,
        "fill_mode": config.fill_mode,
        "entry_threshold": config.entry_threshold,
        "tp_grid": list(config.tp_grid),
        "sl_grid": list(config.sl_grid),
        "cost_sweep_bps": list(config.cost_sweep_bps),
        "primary_tp_pct": config.primary_tp_pct,
        "primary_sl_pct": config.primary_sl_pct,
        "grid": result.grid,
        "baseline": result.baseline,
        "filter_analysis": result.filter_analysis,
        "regime_analysis": result.regime_analysis,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Regime-robustness artifact (written only when the analysis was requested).
    if result.regime_analysis:
        (out_dir / "regime_analysis.json").write_text(
            json.dumps(
                {
                    "n_instances": len(result.instances),
                    "n_symbols": result.n_symbols,
                    "date_min": result.date_min,
                    "date_max": result.date_max,
                    "regime_cost_bps": config.regime_cost_bps,
                    "fill_mode": config.fill_mode,
                    "primary_tp_pct": config.primary_tp_pct,
                    "primary_sl_pct": config.primary_sl_pct,
                    "boundary_fractions": list(config.boundary_fractions),
                    "slippage_levels": list(config.slippage_levels),
                    "regime_analysis": result.regime_analysis,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _format_metrics(m: Dict[str, Any]) -> str:
    if not m or m.get("n_trades", 0) == 0:
        return "n=0"
    return (
        f"n={m['n_trades']} win={m['win_rate']:.1%} "
        f"mean_net={m['mean_net_return_pct']:+.3f}% "
        f"exp={m['expectancy_pct']:+.3f}% "
        f"hold={m['avg_hold_seconds']:.0f}s "
        f"tp/sl/time={m['exit_mix'][EXIT_TP]:.0%}/{m['exit_mix'][EXIT_SL]:.0%}/{m['exit_mix'][EXIT_TIME]:.0%}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Opening gap-up momentum backtest (시초 갭상승) on the 1s STOM DB."
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "_database" / "stock_tick_back.db"),
        help="Path to stock_tick_back.db.",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="Bound the number of symbol tables scanned (0 = full universe).",
    )
    parser.add_argument(
        "--in-sample-fraction",
        type=float,
        default=0.7,
        help="Fraction of distinct session dates used as in-sample (earlier).",
    )
    parser.add_argument("--cost-bps", type=float, default=COST_BPS_ROUND_TRIP)
    parser.add_argument(
        "--artifacts-dir",
        default=str(PROJECT_ROOT / ".omx" / "artifacts" / "gap_up_backtest"),
        help="Where to write per-instance trade artifacts (gitignored).",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write the full result summary as JSON.",
    )
    parser.add_argument(
        "--regime-analysis",
        action="store_true",
        help=(
            "Run the per-year / multi-boundary / slippage regime-robustness "
            "analysis at the realistic cost (--regime-cost-bps)."
        ),
    )
    parser.add_argument(
        "--regime-cost-bps",
        type=float,
        default=REALISTIC_COST_BPS,
        help="Realistic round-trip cost the regime analysis evaluates at (bp).",
    )
    parser.add_argument(
        "--fill-mode",
        choices=["idealized", "realized", "sl_gap_stress"],
        default="idealized",
        help=(
            "TP/SL fill model: idealized (exact levels, default), realized "
            "(actual crossing price), sl_gap_stress (TP conservative + SL "
            "gap-through worst-case)."
        ),
    )
    args = parser.parse_args(argv)

    config = GapUpBacktestConfig(
        db_path=args.db,
        max_symbols=args.max_symbols,
        in_sample_fraction=args.in_sample_fraction,
        cost_bps=args.cost_bps,
        artifacts_dir=args.artifacts_dir,
        regime_analysis=args.regime_analysis,
        regime_cost_bps=args.regime_cost_bps,
        fill_mode=args.fill_mode,
    )
    result = run_gap_up_backtest(config)

    print("=== 시초 갭상승 (opening gap-up) backtest ===")
    print(
        f"instances={len(result.instances)} symbols={result.n_symbols} "
        f"sessions={result.n_sessions} dates={result.date_min}->{result.date_max} "
        f"boundary={result.boundary_date}"
    )
    print(f"entry: 등락율>={config.entry_threshold}%  time-exit={TIME_EXIT_HHMMSS}  cost={config.cost_bps}bp")
    print("-- baseline (buy@open hold->09:25 no TP/SL) --")
    print(f"  in-sample : {_format_metrics(result.baseline.get('in_sample', {}))}")
    print(f"  out-sample: {_format_metrics(result.baseline.get('out_of_sample', {}))}")
    print("-- TP/SL grid (in-sample | out-of-sample) --")
    for cell in result.grid:
        print(
            f"  TP={cell['tp_pct']:g}% SL={cell['sl_pct']:g}%  "
            f"IS[{_format_metrics(cell['in_sample'])}]  "
            f"OOS[{_format_metrics(cell['out_of_sample'])}]"
        )

    # Cost-sweep x filter (PRIMARY TP/SL) + breakeven round-trip cost.
    if result.filter_analysis:
        tp_p, sl_p = config.primary_tp_pct, config.primary_sl_pct
        levels = list(config.cost_sweep_bps)
        print(
            f"-- cost sweep x entry filter (PRIMARY TP={tp_p:g}%/SL={sl_p:g}%) --"
        )
        print(
            "   ref scenarios: Korean-domestic="
            f"{KOREAN_DOMESTIC_COST.total_round_trip_bps():g}bp "
            f"(comm {KOREAN_DOMESTIC_COST.commission_bps_per_side:g}bp/side x2 "
            f"+ tax {KOREAN_DOMESTIC_COST.transaction_tax_bps:g}bp sell-only), "
            "international/low="
            f"{INTERNATIONAL_LOW_COST.total_round_trip_bps():g}bp "
            f"(comm {INTERNATIONAL_LOW_COST.commission_bps_per_side:g}bp/side x2, no tax)"
        )
        header = "  filter    N(IS/OOS)  breakeven(IS/OOS)bp  " + " ".join(
            f"OOS@{int(c)}bp" for c in levels
        )
        print(header)
        for fa in result.filter_analysis:
            sweep = {row["cost_bps"]: row["expectancy_pct"] for row in fa["sweep_out_of_sample"]}

            def _fmt_exp(v: Optional[float]) -> str:
                return "  n=0  " if v is None else f"{v:+.3f}"

            def _fmt_be(v: Optional[float]) -> str:
                return "n/a" if v is None else f"{v:+.1f}"

            cells = " ".join(f"{_fmt_exp(sweep.get(c)):>8}" for c in levels)
            print(
                f"  {fa['filter']:<8}  {fa['n_in_sample']}/{fa['n_out_of_sample']:<6}  "
                f"{_fmt_be(fa['breakeven_bps_in_sample'])}/"
                f"{_fmt_be(fa['breakeven_bps_out_of_sample'])}        {cells}"
            )

    # Regime-robustness analysis (per-year / multi-boundary / slippage).
    if result.regime_analysis:

        def _fmt(v: Optional[float]) -> str:
            return "  n=0  " if v is None else f"{v:+.3f}"

        def _fmt_rate(v: Optional[float]) -> str:
            return " n=0" if v is None else f"{v:4.0%}"

        rc = config.regime_cost_bps
        tp_p, sl_p = config.primary_tp_pct, config.primary_sl_pct
        print(
            f"-- regime robustness (PRIMARY TP={tp_p:g}%/SL={sl_p:g}% @ {rc:g}bp) --"
        )
        for ra in result.regime_analysis:
            years = [r["year"] for r in ra["per_year"]]
            print(f"  [{ra['filter']}] N={ra['n_all']}  per-year expectancy@{rc:g}bp:")
            print(
                "    year :  "
                + "  ".join(f"{y:>7}" for y in years)
            )
            print(
                "    N    :  "
                + "  ".join(f"{r['n_trades']:>7}" for r in ra["per_year"])
            )
            print(
                "    net% :  "
                + "  ".join(f"{_fmt(r['mean_net_return_pct']):>7}" for r in ra["per_year"])
            )
            print(
                "    win  :  "
                + "  ".join(f"{_fmt_rate(r['win_rate']):>7}" for r in ra["per_year"])
            )
            print("    multi-boundary OOS expectancy:")
            for mb in ra["multi_boundary"]:
                print(
                    f"      frac={mb['in_sample_fraction']:.2f} "
                    f"bdy={mb['boundary_date']} "
                    f"N(IS/OOS)={mb['n_in_sample']}/{mb['n_out_of_sample']} "
                    f"IS={_fmt(mb['expectancy_in_sample'])} "
                    f"OOS={_fmt(mb['expectancy_out_of_sample'])}"
                )
            print("    slippage sensitivity (net@cost+slip):")
            for sl in ra["slippage"]:
                print(
                    f"      slip={sl['slippage_bps']:g}bp "
                    f"total={sl['total_cost_bps']:g}bp "
                    f"net={_fmt(sl['expectancy_pct'])}"
                )

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "n_instances": len(result.instances),
                    "n_symbols": result.n_symbols,
                    "n_sessions": result.n_sessions,
                    "date_min": result.date_min,
                    "date_max": result.date_max,
                    "boundary_date": result.boundary_date,
                    "cost_bps": config.cost_bps,
                    "entry_threshold": config.entry_threshold,
                    "tp_grid": list(config.tp_grid),
                    "sl_grid": list(config.sl_grid),
                    "cost_sweep_bps": list(config.cost_sweep_bps),
                    "primary_tp_pct": config.primary_tp_pct,
                    "primary_sl_pct": config.primary_sl_pct,
                    "grid": result.grid,
                    "baseline": result.baseline,
                    "filter_analysis": result.filter_analysis,
                    "regime_analysis": result.regime_analysis,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote summary -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
