"""Follow-up A — symbol leading-zero strip fix (Page 16 prerequisite).

Korean stock codes are 6-digit zero-padded.  Before this fix a candidate CSV
symbol ``000250`` was re-read by pandas as ``int64`` (-> ``250``), which is
internally consistent but mis-joins against the DB table name ``000250`` at the
full-universe boundary.  These tests pin the canonical round-trip and prove the
non-numeric synthetic symbols (e.g. ``"A"``) are left untouched.
"""

import numpy as np
import pandas as pd

from stom_rl.condition_screener import write_candidates
from stom_rl.portfolio_env import PortfolioEnv, PortfolioEnvConfig
from stom_rl.symbol_norm import (
    normalize_symbol,
    normalize_symbol_series,
    read_candidates_csv,
)


def test_normalize_symbol_zero_pads_digits_only():
    # All-digit codes are zero-padded to the canonical 6-digit Korean form.
    assert normalize_symbol("250") == "000250"
    assert normalize_symbol("000250") == "000250"
    assert normalize_symbol(250) == "000250"
    assert normalize_symbol("000100") == "000100"
    # Non-numeric synthetic symbols must be left unchanged (zfill would corrupt).
    assert normalize_symbol("A") == "A"
    assert normalize_symbol("KOSPI200") == "KOSPI200"
    # Missing -> empty so the caller's dropna(subset=["symbol"]) can drop it.
    assert normalize_symbol(np.nan) == ""


def test_normalize_symbol_series_mixed():
    series = pd.Series(["000250", 250, "A", "00000A"])
    out = list(normalize_symbol_series(series))
    assert out == ["000250", "000250", "A", "00000A"]


def _candidates_with_zero_padded_symbol() -> pd.DataFrame:
    """A T+1 candidate frame whose symbol is the zero-padded code 000250."""

    base = pd.Timestamp("2025-07-09 09:00:00")
    series = [100.0, 110.0, 120.0]
    rows = []
    for t, price in enumerate(series):
        fill = series[t + 1] if t + 1 < len(series) else float("nan")
        rows.append(
            {
                "timestamp": (base + pd.Timedelta(seconds=t)).isoformat(),
                "symbol": "000250",
                "condition_id": "zero_pad_fixture",
                "passed": True,
                "rank_score": float(10 - t),
                "price": price,
                "fill_price": fill,
                "fillable": not np.isnan(fill),
                "feature_f": float(t),
            }
        )
    return pd.DataFrame(rows)


def test_symbol_round_trips_zero_padded_through_write_read(tmp_path):
    """000250 must survive write -> read_candidates_csv as 000250 (not 250)."""

    path = tmp_path / "candidates.csv"
    write_candidates(path, _candidates_with_zero_padded_symbol())

    # A bare pandas read strips the leading zeros (this is the bug under test).
    raw = pd.read_csv(path, encoding="utf-8-sig")
    assert str(raw["symbol"].iloc[0]) == "250"

    # The shared helper restores the canonical zero-padded form.
    fixed = read_candidates_csv(path)
    assert list(fixed["symbol"].unique()) == ["000250"]


def test_zero_padded_symbol_buy_sell_matches_holding_key(tmp_path):
    """A buy/sell on a CSV-loaded 000250 candidate matches the env holding key."""

    path = tmp_path / "candidates.csv"
    write_candidates(path, _candidates_with_zero_padded_symbol())

    env = PortfolioEnv(
        PortfolioEnvConfig(
            candidate_path=str(path),
            top_k_candidates=2,
            max_positions=2,
            buy_fraction=0.5,
            cost_bps=0.0,
            seed=7,
        ),
    )
    _, info = env.reset(seed=7)

    # Buy the top candidate; the trade log and the position key are both 000250.
    env.step(1)
    fill = env.trade_log[-1]
    assert fill["symbol"] == "000250"
    assert "000250" in env.account.positions

    # The sell slot resolves the same holding key -> a clean round-trip.
    sell_offset = 1 + env.config.top_k_candidates
    _, _, _, _, info = env.step(sell_offset)
    assert info["trade_count"] == 2
    assert "000250" not in env.account.positions


def test_synthetic_non_numeric_symbol_csv_round_trip_unchanged(tmp_path):
    """A non-numeric symbol 'A' must NOT be zfill-corrupted to '00000A'."""

    frame = pd.DataFrame(
        {
            "timestamp": ["2025-07-09T09:00:00", "2025-07-09T09:00:01"],
            "symbol": ["A", "A"],
            "rank_score": [1.0, 0.5],
            "price": [100.0, 110.0],
        }
    )
    path = tmp_path / "non_numeric.csv"
    write_candidates(path, frame)
    out = read_candidates_csv(path)
    assert list(out["symbol"].unique()) == ["A"]
