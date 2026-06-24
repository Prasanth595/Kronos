"""storage.py — forecast logging + accuracy tracking (SQLite, file-based).

This is the point of the demo account: every forecast is logged at generation
time, and later reconciled against the actual realized close. The dashboard then
surfaces calibration as NUMBERS (band hit-rate, errors), not a vibe.

Headline metric: band hit-rate — a well-calibrated p10-p90 band should contain
the actual ~80% of the time. We report whether it actually does.

Smoke test:  python storage.py
"""

from __future__ import annotations

import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

DEFAULT_DB = os.environ.get(
    "FORECAST_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "forecasts.db"),
)

# Band convention: p10-p90 is a nominal 80% interval.
BAND_NOMINAL_COVERAGE = 0.80


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
# forecast_runs : one row per run_forecast() call.
# forecast_points: one row per (run, horizon) with the band + later the actual.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_runs (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_key   TEXT    NOT NULL,
    ticker_used      TEXT    NOT NULL,
    model_name       TEXT    NOT NULL,
    generated_at     TEXT    NOT NULL,   -- ISO UTC
    last_history_date TEXT   NOT NULL,   -- ISO date of last actual candle
    last_close       REAL    NOT NULL,
    pred_len         INTEGER NOT NULL,
    n_samples        INTEGER NOT NULL,
    used_volume_path INTEGER NOT NULL,
    T                REAL,
    top_p            REAL
);

CREATE TABLE IF NOT EXISTS forecast_points (
    point_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES forecast_runs(run_id) ON DELETE CASCADE,
    instrument_key TEXT  NOT NULL,
    horizon      INTEGER NOT NULL,       -- 1..pred_len
    target_date  TEXT    NOT NULL,       -- ISO date the forecast is for
    p10          REAL    NOT NULL,
    p25          REAL,
    median       REAL    NOT NULL,
    p75          REAL,
    p90          REAL    NOT NULL,
    last_close   REAL    NOT NULL,       -- close at generation (for direction calc)
    actual_close REAL,                   -- filled by update_actuals()
    reconciled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_points_instrument ON forecast_points(instrument_key);
CREATE INDEX IF NOT EXISTS idx_points_target ON forecast_points(target_date);
CREATE INDEX IF NOT EXISTS idx_points_actual ON forecast_points(actual_close);
"""


@contextmanager
def _connect(db_path: str = DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB) -> None:
    """Create tables if they do not exist."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def log_forecast(result, db_path: str = DEFAULT_DB) -> int:
    """Persist a ForecastResult. Returns the run_id.

    Accepts either a ForecastResult object or its to_log_dict() output.
    Idempotent-ish: if an identical run (same instrument + generated date +
    last_history_date) already exists, we skip re-inserting and return that id.
    """
    init_db(db_path)
    data = result.to_log_dict() if hasattr(result, "to_log_dict") else dict(result)

    instrument_key = data["instrument_key"]
    generated_at = data["generated_at"]
    last_history_date = data["last_history_date"]
    gen_date = generated_at[:10]

    with _connect(db_path) as conn:
        # Dedup: same instrument + same calendar day of generation + same history anchor.
        existing = conn.execute(
            """SELECT run_id FROM forecast_runs
               WHERE instrument_key = ? AND substr(generated_at,1,10) = ?
                 AND last_history_date = ?""",
            (instrument_key, gen_date, last_history_date),
        ).fetchone()
        if existing:
            return int(existing["run_id"])

        cur = conn.execute(
            """INSERT INTO forecast_runs
               (instrument_key, ticker_used, model_name, generated_at,
                last_history_date, last_close, pred_len, n_samples,
                used_volume_path, T, top_p)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                instrument_key,
                data["ticker_used"],
                data["model_name"],
                generated_at,
                last_history_date,
                float(data["last_close"]),
                int(data["pred_len"]),
                int(data["n_samples"]),
                1 if data["used_volume_path"] else 0,
                float(data.get("T", 1.0)),
                float(data.get("top_p", 0.9)),
            ),
        )
        run_id = int(cur.lastrowid)

        rows = []
        future_ts = data["future_timestamps"]
        for i, ts in enumerate(future_ts):
            target_date = ts[:10]
            rows.append(
                (
                    run_id,
                    instrument_key,
                    i + 1,
                    target_date,
                    float(data["p10"][i]),
                    float(data["p25"][i]) if data.get("p25") else None,
                    float(data["median"][i]),
                    float(data["p75"][i]) if data.get("p75") else None,
                    float(data["p90"][i]),
                    float(data["last_close"]),
                )
            )
        conn.executemany(
            """INSERT INTO forecast_points
               (run_id, instrument_key, horizon, target_date,
                p10, p25, median, p75, p90, last_close)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        return run_id


def latest_run(instrument_key: str, db_path: str = DEFAULT_DB) -> Optional[dict]:
    """Return the most recent forecast run row for an instrument (or None)."""
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT * FROM forecast_runs
               WHERE instrument_key = ?
               ORDER BY generated_at DESC LIMIT 1""",
            (instrument_key,),
        ).fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------------- #
# Reconciliation against actuals
# --------------------------------------------------------------------------- #
def update_actuals(instrument_key: Optional[str] = None,
                   db_path: str = DEFAULT_DB,
                   fetch_fn=None) -> int:
    """Fetch realized closes for past forecast points whose target date has passed.

    Args:
        instrument_key: limit to one instrument, or None for all.
        fetch_fn:       callable(instrument_key) -> DataFrame with
                        columns 'timestamps','close'. Defaults to
                        forecast_engine.fetch_ohlcv.

    Returns the number of points newly reconciled.
    """
    init_db(db_path)
    if fetch_fn is None:
        from forecast_engine import fetch_ohlcv as fetch_fn  # lazy import

    today = pd.Timestamp(datetime.now(timezone.utc).date())

    with _connect(db_path) as conn:
        instruments = (
            [instrument_key]
            if instrument_key
            else [r["instrument_key"] for r in conn.execute(
                "SELECT DISTINCT instrument_key FROM forecast_points")]
        )

        total = 0
        for inst_key in instruments:
            pending = conn.execute(
                """SELECT point_id, target_date FROM forecast_points
                   WHERE instrument_key = ? AND actual_close IS NULL
                     AND target_date <= ?""",
                (inst_key, today.date().isoformat()),
            ).fetchall()
            if not pending:
                continue

            try:
                actuals = fetch_fn(inst_key)
            except Exception:  # noqa: BLE001 - skip instrument on fetch failure
                continue
            if actuals is None or len(actuals) == 0:
                continue

            close_by_date = {
                pd.Timestamp(t).date().isoformat(): float(c)
                for t, c in zip(actuals["timestamps"], actuals["close"])
            }

            now_iso = datetime.now(timezone.utc).isoformat()
            for row in pending:
                actual = close_by_date.get(row["target_date"])
                if actual is None:
                    continue  # market may have been closed that day; try later
                conn.execute(
                    """UPDATE forecast_points
                       SET actual_close = ?, reconciled_at = ?
                       WHERE point_id = ?""",
                    (actual, now_iso, row["point_id"]),
                )
                total += 1
        return total


# --------------------------------------------------------------------------- #
# Accuracy summary
# --------------------------------------------------------------------------- #
def accuracy_summary(instrument_key: str,
                     db_path: str = DEFAULT_DB,
                     min_points: int = 10) -> dict:
    """Compute calibration / accuracy stats for reconciled forecast points.

    Returns a dict with:
        n_reconciled, enough_data (bool), min_points,
        band_hit_rate            (fraction of actuals inside p10-p90),
        band_nominal             (0.80 — what a calibrated band should hit),
        calibration_note         (plain-English read),
        median_abs_error,        (|actual - median|, absolute)
        median_abs_pct_error,    (as % of actual)
        directional_accuracy,    (did median imply the realized direction?)
        by_horizon               (DataFrame-as-records for per-horizon hit-rate)
    """
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT horizon, target_date, p10, median, p90, last_close, actual_close
               FROM forecast_points
               WHERE instrument_key = ? AND actual_close IS NOT NULL
               ORDER BY target_date""",
            (instrument_key,),
        ).fetchall()

    n = len(rows)
    result = {
        "instrument_key": instrument_key,
        "n_reconciled": n,
        "min_points": min_points,
        "enough_data": n >= min_points,
        "band_nominal": BAND_NOMINAL_COVERAGE,
        "band_hit_rate": None,
        "median_abs_error": None,
        "median_abs_pct_error": None,
        "directional_accuracy": None,
        "calibration_note": None,
        "by_horizon": [],
    }
    if n == 0:
        result["calibration_note"] = "No reconciled forecasts yet."
        return result

    df = pd.DataFrame([dict(r) for r in rows])
    inside = (df["actual_close"] >= df["p10"]) & (df["actual_close"] <= df["p90"])
    abs_err = (df["actual_close"] - df["median"]).abs()
    abs_pct = (abs_err / df["actual_close"].abs()).replace([np.inf, -np.inf], np.nan)

    pred_dir = np.sign(df["median"] - df["last_close"])
    real_dir = np.sign(df["actual_close"] - df["last_close"])
    # Only count points where the forecast actually implied a direction.
    dir_mask = pred_dir != 0
    dir_acc = float((pred_dir[dir_mask] == real_dir[dir_mask]).mean()) if dir_mask.any() else None

    band_hit = float(inside.mean())
    result["band_hit_rate"] = band_hit
    result["median_abs_error"] = float(abs_err.median())
    result["median_abs_pct_error"] = float(abs_pct.median()) if abs_pct.notna().any() else None
    result["directional_accuracy"] = dir_acc

    # Per-horizon hit-rate
    by_h = (
        df.assign(inside=inside)
        .groupby("horizon")
        .agg(n=("inside", "size"), hit_rate=("inside", "mean"),
             median_abs_error=("actual_close", lambda s: float((s - df.loc[s.index, "median"]).abs().median())))
        .reset_index()
    )
    result["by_horizon"] = by_h.to_dict(orient="records")

    # Plain-English calibration note (honest about small samples).
    if n < min_points:
        result["calibration_note"] = (
            f"Not enough logged forecasts yet ({n} reconciled, need >= {min_points}). "
            "Treat numbers below as provisional."
        )
    else:
        pct = band_hit * 100
        nominal = BAND_NOMINAL_COVERAGE * 100
        if band_hit >= 0.75:
            cal = f"Band hit-rate {pct:.0f}% vs nominal {nominal:.0f}% -> roughly calibrated."
        elif band_hit >= 0.6:
            cal = (f"Band hit-rate {pct:.0f}% vs nominal {nominal:.0f}% -> band is somewhat "
                   "too NARROW (overconfident).")
        else:
            cal = (f"Band hit-rate {pct:.0f}% vs nominal {nominal:.0f}% -> band is much too "
                   "NARROW; the model is overconfident on this instrument.")
        result["calibration_note"] = cal

    return result


# --------------------------------------------------------------------------- #
# Smoke test (SCOPE.md §9 step 3)
# --------------------------------------------------------------------------- #
def _smoke_test():
    import tempfile

    tmp = os.path.join(tempfile.gettempdir(), "kronos_storage_smoke.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    print("storage smoke test ->", tmp)
    init_db(tmp)

    # Build a fake forecast for dates in the past so update_actuals can reconcile.
    base = pd.Timestamp(datetime.now(timezone.utc).date()) - pd.Timedelta(days=10)
    future_ts = [(base + pd.offsets.BDay(i + 1)).isoformat() for i in range(5)]
    fake = {
        "instrument_key": "gold",
        "ticker_used": "GC=F",
        "model_name": "NeoQuasar/Kronos-small",
        "generated_at": base.isoformat(),
        "last_history_date": base.isoformat(),
        "last_close": 2000.0,
        "pred_len": 5,
        "n_samples": 30,
        "used_volume_path": True,
        "T": 1.0,
        "top_p": 0.9,
        "future_timestamps": future_ts,
        "p10": [1950, 1940, 1930, 1920, 1910],
        "p25": [1975, 1970, 1965, 1960, 1955],
        "median": [2005, 2010, 2015, 2020, 2025],
        "p75": [2035, 2045, 2055, 2065, 2075],
        "p90": [2060, 2080, 2100, 2120, 2140],
    }
    run_id = log_forecast(fake, db_path=tmp)
    print(f"Logged run_id={run_id}")

    # Fake actuals fetcher: returns a close inside the band for each target date.
    def fake_fetch(instrument_key):
        dates = [pd.Timestamp(t) for t in future_ts]
        closes = [2003, 2012, 1925, 2030, 2200]  # mix: in-band, in-band, below p10, in-band, above p90
        return pd.DataFrame({"timestamps": dates, "close": closes})

    n = update_actuals("gold", db_path=tmp, fetch_fn=fake_fetch)
    print(f"Reconciled {n} points")

    summary = accuracy_summary("gold", db_path=tmp, min_points=3)
    print("Accuracy summary:")
    for k, v in summary.items():
        if k == "by_horizon":
            print(f"  by_horizon: {len(v)} rows")
        else:
            print(f"  {k}: {v}")

    assert summary["n_reconciled"] == 5
    # 3 of 5 inside band -> 0.6 hit rate
    assert abs(summary["band_hit_rate"] - 0.6) < 1e-9, summary["band_hit_rate"]
    print("\n[OK] storage smoke test passed.")


if __name__ == "__main__":
    _smoke_test()
