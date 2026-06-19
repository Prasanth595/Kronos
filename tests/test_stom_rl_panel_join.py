"""Tests for Page 7.5 multi-symbol 1s time-sync panel join (the leakage gate).

These tests use a tiny in-memory / temp sqlite fixture with 2-3 symbols and
UTF-8 Korean column names.  They have NO dependency on the 29.7GB production DB.

Coverage:
* (a) symbols aligned on a common timestamp grid;
* (b) a symbol with a halt/gap yields NaN (or exclusion), never a future value;
* (c) injecting a future-dated row does NOT change any row at-or-before T
  (the core leakage guard for the as-of backward join);
* (d) determinism — repeated joins produce identical output.
Plus the memory precondition (P2-1) and the DB-backed convenience path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from finetune.qlib_stom_pipeline import STOM_RL_CANONICAL_FEATURES
from stom_rl.panel_join import (
    DEFAULT_MEMORY_BUDGET_BYTES,
    PANEL_LONG_COLUMNS,
    SymbolFrame,
    assert_panel_memory_budget,
    build_panel_from_db,
    estimate_panel_memory,
    join_symbol_frames,
    prepare_symbol_frame,
)

# STOM tick DB column order (UTF-8 Korean names), trimmed to the RL-export
# fields.  Mirrors the real per-symbol table layout (see Page 7 fixture).
_FIXTURE_COLUMNS = [
    "index",
    "현재가",
    "시가",
    "고가",
    "저가",
    "초당매수수량",
    "초당매도수량",
    "체결강도",
    "초당거래대금",
    "회전율",
    "매수총잔량",
    "매도총잔량",
    "매수호가1",
    "매도호가1",
]


def _fixture_row(idx: int, close: float, buy: float, sell: float, amount: float, strength: float = 200.0) -> tuple:
    return (
        idx,
        close,
        close,
        close + 10.0,
        close - 10.0,
        buy,
        sell,
        strength,
        amount,
        0.05,
        80.0,
        20.0,
        close - 10.0,
        close + 10.0,
    )


def _make_multi_symbol_db(db_path: Path, tables: dict[str, list[tuple]]) -> None:
    """Create a tiny multi-symbol STOM-shaped DB with UTF-8 Korean columns."""

    conn = sqlite3.connect(str(db_path))
    try:
        column_defs = ", ".join(f'"{name}"' for name in _FIXTURE_COLUMNS)
        placeholders = ", ".join(["?"] * len(_FIXTURE_COLUMNS))
        for table_name, rows in tables.items():
            conn.execute(f'CREATE TABLE "{table_name}" ({column_defs})')
            conn.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows)
        conn.commit()
    finally:
        conn.close()


def _make_keyed_frame(symbol: str, seconds: list[int], base: float = 100.0) -> pd.DataFrame:
    """Build a keyed canonical frame (timestamp,symbol,session,<14 features>).

    ``seconds`` are second-offsets from 2022-12-12 09:00:00.  Feature values are
    deterministic functions of the offset so cross-symbol leakage is detectable.
    """

    ts = [pd.Timestamp("2022-12-12 09:00:00") + pd.Timedelta(seconds=s) for s in seconds]
    n = len(seconds)
    data = {
        "timestamp": ts,
        "symbol": [symbol] * n,
        "session": ["20221212"] * n,
    }
    for i, feat in enumerate(STOM_RL_CANONICAL_FEATURES):
        # close carries a recognisable point-in-time value: base + second offset.
        if feat == "close":
            data[feat] = [base + s for s in seconds]
        else:
            data[feat] = [float(i) + float(s) for s in seconds]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# (a) common-grid alignment
# ---------------------------------------------------------------------------
def test_symbols_aligned_on_common_grid():
    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3]))
    b = prepare_symbol_frame(_make_keyed_frame("000040", [0, 2, 4]))

    panel, report = join_symbol_frames([a, b])

    assert list(panel.columns) == PANEL_LONG_COLUMNS
    # Common grid is the union of observed seconds: {0,1,2,3,4} -> 5 timestamps.
    grid = sorted(panel["timestamp"].unique())
    assert len(grid) == 5
    assert report.grid_size == 5
    # Every grid timestamp carries exactly one row per symbol (long format).
    counts = panel.groupby("timestamp")["symbol"].nunique()
    assert (counts == 2).all()
    # Both symbols share the identical timestamp grid.
    for sym in ("000020", "000040"):
        sym_ts = sorted(panel.loc[panel["symbol"] == sym, "timestamp"].unique())
        assert sym_ts == grid


# ---------------------------------------------------------------------------
# (b) halt / gap -> NaN (or exclusion), never a future value
# ---------------------------------------------------------------------------
def test_gap_yields_nan_not_future_value():
    # Symbol B is "halted" between second 1 and second 4: it has observations at
    # t=0 and t=5 only.  At grid times 1..4 the as-of (backward) value must be
    # B's t=0 observation (stale-but-real), and NEVER its t=5 future value.
    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3, 4, 5]))
    b = prepare_symbol_frame(_make_keyed_frame("000040", [0, 5], base=500.0))

    panel, _ = join_symbol_frames([a, b])

    b_rows = panel[panel["symbol"] == "000040"].set_index("timestamp")["close"]
    t = pd.Timestamp("2022-12-12 09:00:00")
    # At the halted seconds 1..4 the value is the stale t=0 close (500.0),
    # which is strictly LESS than the future t=5 close (505.0).
    for s in (1, 2, 3, 4):
        assert b_rows[t + pd.Timedelta(seconds=s)] == 500.0
        assert b_rows[t + pd.Timedelta(seconds=s)] != 505.0
    assert b_rows[t + pd.Timedelta(seconds=5)] == 505.0


def test_no_observation_before_grid_start_is_nan_not_future():
    # Symbol B's first observation is at t=3; grid starts at t=0 (from A).
    # Grid times 0,1,2 have NO B observation at-or-before them -> must be NaN,
    # never B's future t=3 value.
    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3]))
    b = prepare_symbol_frame(_make_keyed_frame("000040", [3], base=900.0))

    panel, report = join_symbol_frames([a, b])

    b_rows = panel[panel["symbol"] == "000040"].set_index("timestamp")["close"]
    t = pd.Timestamp("2022-12-12 09:00:00")
    for s in (0, 1, 2):
        assert pd.isna(b_rows[t + pd.Timedelta(seconds=s)])
    assert b_rows[t + pd.Timedelta(seconds=3)] == 903.0
    assert report.per_symbol["000040"]["grid_rows_nan"] == 3


def test_halt_rows_with_nonpositive_close_are_excluded_and_reported():
    frame = _make_keyed_frame("000020", [0, 1, 2, 3])
    # Mark seconds 1 and 2 as a trading halt (close <= 0).
    frame.loc[frame.index[1:3], "close"] = 0.0
    sf = prepare_symbol_frame(frame)

    assert sf.excluded_halt_rows == 2
    # Remaining observations are only the tradable seconds 0 and 3.
    kept = sf.frame["timestamp"].dt.second.tolist()
    assert kept == [0, 3]


# ---------------------------------------------------------------------------
# (c) leakage guard: injecting a future-dated row must not change rows <= T
# ---------------------------------------------------------------------------
def test_injecting_future_row_does_not_change_rows_at_or_before_T():
    """Core leakage assertion for the as-of backward join.

    Build a panel from baseline observations, then rebuild it after injecting a
    far-future, extreme-valued row for one symbol.  Every panel row whose
    timestamp is at-or-before the last baseline grid time T must be byte-for-byte
    identical between the two runs.  A backward as-of join guarantees this; any
    forward/leaking fill would change the <= T rows.
    """

    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3, 4]))
    b_base = _make_keyed_frame("000040", [0, 1, 2, 3, 4], base=200.0)
    b_future = pd.concat(
        [b_base, _make_keyed_frame("000040", [600], base=999999.0)],
        ignore_index=True,
    )

    baseline_panel, _ = join_symbol_frames([a, prepare_symbol_frame(b_base)])
    future_panel, _ = join_symbol_frames([a, prepare_symbol_frame(b_future)])

    last_baseline_T = baseline_panel["timestamp"].max()

    # Restrict both panels to rows at-or-before the last baseline grid time T.
    base_leq = baseline_panel[baseline_panel["timestamp"] <= last_baseline_T].reset_index(drop=True)
    fut_leq = (
        future_panel[future_panel["timestamp"] <= last_baseline_T]
        .reset_index(drop=True)
    )

    # Same shape and byte-identical features at every row <= T.
    assert base_leq.shape == fut_leq.shape
    pd.testing.assert_frame_equal(base_leq, fut_leq)

    # And the injected future value (999999.0) appears nowhere in the <= T panel.
    assert not (fut_leq[STOM_RL_CANONICAL_FEATURES] >= 999999.0).any().any()


def test_tolerance_treats_long_staleness_as_missing():
    # With a 2s tolerance, B's t=0 obs cannot fill grid times beyond t=2.
    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3, 4, 5]))
    b = prepare_symbol_frame(_make_keyed_frame("000040", [0, 5], base=500.0))

    panel, _ = join_symbol_frames([a, b], tolerance=pd.Timedelta(seconds=2))

    b_rows = panel[panel["symbol"] == "000040"].set_index("timestamp")["close"]
    t = pd.Timestamp("2022-12-12 09:00:00")
    assert b_rows[t + pd.Timedelta(seconds=2)] == 500.0  # within tolerance
    assert pd.isna(b_rows[t + pd.Timedelta(seconds=3)])  # stale beyond tolerance
    assert pd.isna(b_rows[t + pd.Timedelta(seconds=4)])
    assert b_rows[t + pd.Timedelta(seconds=5)] == 505.0  # fresh obs


# ---------------------------------------------------------------------------
# (d) determinism
# ---------------------------------------------------------------------------
def test_join_is_deterministic():
    frames = [
        prepare_symbol_frame(_make_keyed_frame("000040", [0, 2, 4])),
        prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3, 4])),
    ]
    panel1, _ = join_symbol_frames(frames)
    # Rebuild from scratch (fresh objects) and re-join in a different input order.
    frames2 = [
        prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2, 3, 4])),
        prepare_symbol_frame(_make_keyed_frame("000040", [0, 2, 4])),
    ]
    panel2, _ = join_symbol_frames(frames2)

    pd.testing.assert_frame_equal(panel1, panel2)


# ---------------------------------------------------------------------------
# Memory precondition (P2-1)
# ---------------------------------------------------------------------------
def test_memory_estimate_and_budget_precondition():
    est = estimate_panel_memory(max_symbols=3, max_rows_per_group=10)
    assert est["max_symbols"] == 3
    assert est["estimated_bytes"] > 0

    ok = assert_panel_memory_budget(max_symbols=3, max_rows_per_group=1000)
    assert ok["within_budget"] is True
    assert ok["budget_bytes"] == DEFAULT_MEMORY_BUDGET_BYTES


def test_memory_budget_rejects_oversized_chunk():
    with pytest.raises(MemoryError):
        # 2400 symbols x 23400 seconds (full session) x 112 bytes/row >> 1MB budget.
        assert_panel_memory_budget(
            max_symbols=2400,
            max_rows_per_group=23400,
            budget_bytes=1_000_000,
        )


# ---------------------------------------------------------------------------
# DB-backed convenience path (per-day-chunk; no full scan)
# ---------------------------------------------------------------------------
def test_build_panel_from_db_multi_symbol(tmp_path: Path):
    db_path = tmp_path / "fixture.db"
    rows_a = [
        _fixture_row(20221212090005 + i, close=9260.0 + i, buy=10.0 + i, sell=3.0, amount=100.0 + i)
        for i in range(6)
    ]
    # Symbol B has a gap: observations only at +0 and +5 seconds.
    rows_b = [
        _fixture_row(20221212090005, close=5000.0, buy=4.0, sell=1.0, amount=50.0),
        _fixture_row(20221212090010, close=5005.0, buy=4.0, sell=1.0, amount=55.0),
    ]
    _make_multi_symbol_db(db_path, {"000020": rows_a, "000040": rows_b})

    panel, report = build_panel_from_db(
        db_path=db_path,
        tables=["000020", "000040"],
        session="20221212",
        time_start="090000",
        time_end="093000",
    )

    assert list(panel.columns) == PANEL_LONG_COLUMNS
    assert set(report.symbols) == {"000020", "000040"}
    assert report.grid_size == 6  # union of A's 6 seconds (B's seconds subset)
    # Long format: 6 grid timestamps x 2 symbols = 12 rows.
    assert len(panel) == 12
    # B has only 2 real observations on a 6-row grid -> 4 backward-filled rows,
    # all stale-but-real (never future). No NaN here because B starts at the grid
    # start; the value at the gapped seconds equals B's last close 5000.0.
    b_rows = panel[panel["symbol"] == "000040"].set_index("timestamp")["close"]
    t = pd.Timestamp("2022-12-12 09:00:05")
    assert b_rows[t + pd.Timedelta(seconds=1)] == 5000.0  # stale, not the future 5005
    assert b_rows[t + pd.Timedelta(seconds=5)] == 5005.0


def test_empty_symbol_frame_is_all_nan_not_future():
    a = prepare_symbol_frame(_make_keyed_frame("000020", [0, 1, 2]))
    empty = SymbolFrame(
        symbol="000099",
        frame=pd.DataFrame(columns=["timestamp", "symbol", *STOM_RL_CANONICAL_FEATURES]),
    )
    panel, report = join_symbol_frames([a, empty])

    empty_rows = panel[panel["symbol"] == "000099"]
    assert len(empty_rows) == 3
    assert empty_rows[STOM_RL_CANONICAL_FEATURES].isna().all().all()
    assert report.per_symbol["000099"]["grid_rows_nan"] == 3


def _make_minutes_db(db_path: Path, symbol: str, n_minutes: int, secs_per_min: int) -> None:
    """Build a single-symbol DB spanning ``n_minutes`` × ``secs_per_min`` seconds.

    Timestamps run 09:00:00, 09:00:01, ... so the live feed path can be exercised
    at both 1s and 1min grids without the production DB.
    """

    rows = []
    base = pd.Timestamp("2022-12-12 09:00:00")
    counter = 0
    for minute in range(n_minutes):
        for sec in range(secs_per_min):
            t = base + pd.Timedelta(minutes=minute, seconds=sec)
            idx = int(t.strftime("%Y%m%d%H%M%S"))
            # close drifts up over the session; flow varies per second.
            rows.append(
                _fixture_row(
                    idx,
                    close=9260.0 + counter * 0.5,
                    buy=10.0 + (counter % 7),
                    sell=3.0 + (counter % 5),
                    amount=100.0 + (counter % 11) * 10.0,
                    strength=180.0 + (counter % 13) * 5.0,
                )
            )
            counter += 1
    _make_multi_symbol_db(db_path, {symbol: rows})


def test_build_panel_from_db_freq_1min_resamples_live_feed(tmp_path: Path):
    """The live feed path (build_panel_from_db) at freq='1min' resamples the RL
    SOURCE frame to 1-min bars: far fewer timestamps than 1s, flow summed, and
    the 22 canonical features (incl. the 4 trend features) present + non-degenerate."""

    db_path = tmp_path / "minutes.db"
    n_minutes, secs_per_min = 6, 12
    _make_minutes_db(db_path, "000020", n_minutes=n_minutes, secs_per_min=secs_per_min)

    panel_1s, report_1s = build_panel_from_db(
        db_path=db_path, tables=["000020"], session="20221212", freq="1s"
    )
    panel_1min, report_1min = build_panel_from_db(
        db_path=db_path, tables=["000020"], session="20221212", freq="1min"
    )

    assert list(panel_1min.columns) == PANEL_LONG_COLUMNS
    # 1-min grid has ~one bar per minute, far fewer than the per-second grid.
    assert report_1min.grid_size == n_minutes
    assert report_1s.grid_size == n_minutes * secs_per_min
    assert report_1min.grid_size < report_1s.grid_size

    # Bars labeled at bucket start (floor to minute), one per minute.
    minute_stamps = sorted(panel_1min["timestamp"].unique())
    assert len(minute_stamps) == n_minutes
    assert pd.Timestamp(minute_stamps[0]) == pd.Timestamp("2022-12-12 09:00:00")

    # V-NONDEGEN on the live feed: the trend + flow/rate features must vary.
    sym = panel_1min[panel_1min["symbol"] == "000020"]
    for col in (
        "amount",
        "volume",
        "trade_strength",
        "moving_average_n",
        "amount_slope_n",
    ):
        assert float(sym[col].var()) > 0.0, f"{col!r} degenerate on the 1-min live-feed panel"

    # Flow is SUMMED per minute: the 1-min volume of the first bar equals the sum
    # of the per-second volumes in that minute (each second volume = buy+sell).
    expected_first_volume = sum(
        (10.0 + (i % 7)) + (3.0 + (i % 5)) for i in range(secs_per_min)
    )
    first_bar = sym.sort_values("timestamp").iloc[0]
    assert first_bar["volume"] == pytest.approx(expected_first_volume)
