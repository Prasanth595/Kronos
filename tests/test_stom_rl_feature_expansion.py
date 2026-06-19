import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from finetune.qlib_stom_pipeline import (
    STOM_RL_CANONICAL_FEATURES,
    STOM_RL_TRADE_STRENGTH_AVG_WINDOW,
    STOM_RL_TREND_WINDOW,
    STOM_RL_VOLATILITY_DDOF,
    build_stom_rl_feature_frame,
    export_stom_rl_features,
    resample_stom_rl_source_frame,
)
from stom_rl.trading_env import StomTickTradingEnv, StomTickTradingEnvConfig


# STOM tick DB column order (UTF-8 Korean names), trimmed to the fields needed
# by the RL feature export.  Mirrors the real per-symbol table layout so the
# export path can be exercised without the 29.7GB production database.
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
    "등락율",
    "시가총액",
    "고저평균대비등락율",
]


def _make_fixture_db(db_path: Path, rows: list[tuple]) -> None:
    """Create a tiny STOM-shaped sqlite DB with UTF-8 Korean column names."""

    conn = sqlite3.connect(str(db_path))
    try:
        column_defs = ", ".join(f'"{name}"' for name in _FIXTURE_COLUMNS)
        conn.execute(f'CREATE TABLE "000020" ({column_defs})')
        placeholders = ", ".join(["?"] * len(_FIXTURE_COLUMNS))
        conn.executemany(f'INSERT INTO "000020" VALUES ({placeholders})', rows)
        conn.commit()
    finally:
        conn.close()


def _fixture_row(idx: int, close: float, buy: float, sell: float, amount: float, strength: float = 200.0) -> tuple:
    # index, 현재가, 시가, 고가, 저가, 초당매수수량, 초당매도수량, 체결강도,
    # 초당거래대금, 회전율, 매수총잔량, 매도총잔량, 매수호가1, 매도호가1,
    # 등락율, 시가총액, 고저평균대비등락율
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
        1.25,
        45000.0,
        -0.5,
    )


def test_build_stom_rl_feature_frame_maps_db_like_columns():
    frame = pd.DataFrame(
        {
            "symbol": ["000001", "000001"],
            "session": ["20250103", "20250103"],
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100, 101],
            "volume": [10, 11],
            "amount": [1000, 1111],
            "trade_strength": [600, 250],
            "buy_qty": [7, 9],
            "sell_qty": [2, 3],
            "bid_qty": [80, 90],
            "ask_qty": [20, 30],
            "bid_price": [99, 100],
            "ask_price": [101, 102],
            "turnover_rate": [1.5, 1.7],
        }
    )

    features = build_stom_rl_feature_frame(frame)

    assert list(features.columns) == STOM_RL_CANONICAL_FEATURES
    assert features["trade_strength"].iloc[0] == 500
    assert features["net_buy_qty_1s"].tolist() == [5, 6]
    assert features["bid_ask_imbalance"].iloc[0] == pytest.approx(0.8)
    assert features["spread_ticks"].iloc[0] == pytest.approx(2.0)
    assert features["amount_delta"].tolist() == [0.0, 111.0]


def test_trading_env_accepts_configured_extra_feature_columns(tmp_path: Path):
    csv_path = tmp_path / "KR000001_20250103.csv"
    base = pd.Timestamp("2025-01-03 09:00:00")
    rows = 16
    frame = pd.DataFrame(
        {
            "symbol": "KR000001",
            "date": [(base + pd.Timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(rows)],
            "open": np.arange(rows) + 100.0,
            "high": np.arange(rows) + 101.0,
            "low": np.arange(rows) + 99.0,
            "close": np.arange(rows) + 100.0,
            "volume": np.arange(rows) + 10.0,
            "amount": (np.arange(rows) + 100.0) * (np.arange(rows) + 10.0),
            "trade_strength": np.arange(rows) + 200.0,
            "net_buy_qty_1s": np.arange(rows) - 2.0,
        }
    )
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "episodes": [
                    {
                        "episode_id": "000001_20250103",
                        "symbol": "000001",
                        "session": "20250103",
                        "split": "train",
                        "source_csv": str(csv_path),
                    }
                ]
            }
        ),
        encoding="utf-8-sig",
    )

    env = StomTickTradingEnv(
        StomTickTradingEnvConfig(
            manifest_path=str(manifest_path),
            split="train",
            lookback_window=5,
            reward_horizon_seconds=3,
            feature_columns=("open", "close", "trade_strength", "net_buy_qty_1s"),
        )
    )
    observation, info = env.reset(seed=1)

    assert observation.shape == (5, 7)
    assert info["feature_columns"] == [
        "open",
        "close",
        "trade_strength",
        "net_buy_qty_1s",
        "position",
        "unrealized_return",
        "time_in_position",
    ]


def test_export_stom_rl_features_yields_canonical_columns(tmp_path: Path):
    db_path = tmp_path / "fixture.db"
    rows = [
        _fixture_row(20221212090005 + i, close=9260.0 + i, buy=10.0 + i, sell=3.0 + i, amount=100.0 + i)
        for i in range(8)
    ]
    _make_fixture_db(db_path, rows)

    report = export_stom_rl_features(
        db_path=db_path,
        output_dir=tmp_path / "out",
        table="000020",
        session="20221212",
        time_start="090000",
        time_end="093000",
        max_rows=5000,
    )

    csv_path = Path(report["csv_path"])
    assert csv_path.exists()
    frame = pd.read_csv(csv_path, dtype={"symbol": str, "session": str}, encoding="utf-8-sig")

    feature_columns = [c for c in frame.columns if c in STOM_RL_CANONICAL_FEATURES]
    assert feature_columns == STOM_RL_CANONICAL_FEATURES
    assert list(frame.columns)[:3] == ["timestamp", "symbol", "session"]

    assert report["source"]["row_count"] == 8
    assert report["source"]["unresolved_targets"] == []
    assert report["source"]["encoding_confirmed"] is True
    assert frame["symbol"].iloc[0] == "000020"


def test_export_stom_rl_features_has_no_nan_or_inf(tmp_path: Path):
    db_path = tmp_path / "fixture.db"
    rows = [
        _fixture_row(20221212090005 + i, close=9260.0, buy=0.0, sell=0.0, amount=0.0)
        for i in range(5)
    ]
    _make_fixture_db(db_path, rows)

    report = export_stom_rl_features(
        db_path=db_path,
        output_dir=tmp_path / "out",
        table="000020",
        session="20221212",
    )

    assert report["scale"]["nan_inf_clean"] is True
    assert report["scale"]["has_nan"] is False
    assert report["scale"]["has_inf"] is False

    frame = pd.read_csv(Path(report["csv_path"]), encoding="utf-8-sig")
    feature_frame = frame[STOM_RL_CANONICAL_FEATURES]
    assert not feature_frame.isna().any().any()
    assert np.isfinite(feature_frame.to_numpy(dtype="float64")).all()


def test_export_stom_rl_features_is_leakage_free(tmp_path: Path):
    """A future-dated row beyond the window must not change features at rows <= T."""

    base_rows = [
        _fixture_row(20221212090005 + i, close=9260.0 + i, buy=10.0 + i, sell=3.0, amount=100.0 + i)
        for i in range(6)
    ]
    # A row outside the 09:00-09:30 window with extreme values that would shift
    # scale/diff features if it ever leaked backward into <= T rows.
    future_row = _fixture_row(20221212094000, close=99999.0, buy=99999.0, sell=99999.0, amount=99999.0)

    db_baseline = tmp_path / "baseline.db"
    db_with_future = tmp_path / "with_future.db"
    _make_fixture_db(db_baseline, base_rows)
    _make_fixture_db(db_with_future, base_rows + [future_row])

    report_baseline = export_stom_rl_features(
        db_path=db_baseline,
        output_dir=tmp_path / "out_baseline",
        table="000020",
        session="20221212",
        time_start="090000",
        time_end="093000",
    )
    report_future = export_stom_rl_features(
        db_path=db_with_future,
        output_dir=tmp_path / "out_future",
        table="000020",
        session="20221212",
        time_start="090000",
        time_end="093000",
    )

    frame_baseline = pd.read_csv(Path(report_baseline["csv_path"]), encoding="utf-8-sig")
    frame_future = pd.read_csv(Path(report_future["csv_path"]), encoding="utf-8-sig")

    # The window filter drops the future row, so both frames must be identical.
    assert frame_baseline.shape == frame_future.shape
    pd.testing.assert_frame_equal(
        frame_baseline[STOM_RL_CANONICAL_FEATURES],
        frame_future[STOM_RL_CANONICAL_FEATURES],
    )

    # Point-in-time check: amount_delta at row T equals amount[T] - amount[T-1]
    # (backward-only differencing, never forward-looking).
    amount = frame_baseline["amount"].to_numpy(dtype="float64")
    amount_delta = frame_baseline["amount_delta"].to_numpy(dtype="float64")
    assert amount_delta[0] == 0.0
    np.testing.assert_allclose(amount_delta[1:], amount[1:] - amount[:-1])


# ---------------------------------------------------------------------------
# Stage C feature expansion: the 4 new canonical features.
# ---------------------------------------------------------------------------
def test_build_stom_rl_feature_frame_adds_stage_c_features():
    """The 4 Stage C features are produced from DB-like Korean columns and
    are finite (no NaN/inf)."""

    n = 6
    frame = pd.DataFrame(
        {
            "symbol": ["000001"] * n,
            "session": ["20250103"] * n,
            "open": np.arange(n) + 100.0,
            "high": np.arange(n) + 101.0,
            "low": np.arange(n) + 99.0,
            "close": np.arange(n) + 100.0,
            "volume": np.arange(n) + 10.0,
            "amount": (np.arange(n) + 100.0) * 5.0,
            "체결강도": np.arange(n) + 200.0,
            "등락율": np.linspace(-2.0, 3.0, n),
            "시가총액": np.full(n, 45000.0),
            "고저평균대비등락율": np.linspace(-1.0, 1.0, n),
        }
    )

    features = build_stom_rl_feature_frame(frame)

    # Canonical set is now 22 wide (18 Stage-C + 4 Stage-2 trend features).
    assert len(STOM_RL_CANONICAL_FEATURES) == 22
    for new_col in (
        "change_rate",
        "market_cap",
        "high_low_mid_change_rate",
        "trade_strength_avg_n",
    ):
        assert new_col in features.columns

    block = features[
        ["change_rate", "market_cap", "high_low_mid_change_rate", "trade_strength_avg_n"]
    ]
    assert not block.isna().any().any()
    assert np.isfinite(block.to_numpy(dtype="float64")).all()

    # Direct passthroughs map their source column values.
    np.testing.assert_allclose(features["change_rate"].to_numpy(), np.linspace(-2.0, 3.0, n))
    np.testing.assert_allclose(
        features["high_low_mid_change_rate"].to_numpy(), np.linspace(-1.0, 1.0, n)
    )
    # market_cap is log1p-normalized from the large 시가총액 magnitude.
    np.testing.assert_allclose(features["market_cap"].to_numpy(), np.log1p(45000.0))


def test_trade_strength_avg_n_is_causal_trailing_mean():
    """``trade_strength_avg_n`` at row T equals the trailing mean of
    trade_strength over rows <= T, and is UNCHANGED when future rows are
    appended or modified (no look-ahead)."""

    window = STOM_RL_TRADE_STRENGTH_AVG_WINDOW
    n = 40
    strengths = (np.arange(n) % 7) * 30.0 + 50.0  # within the [0, 500] band

    def _frame(values: np.ndarray) -> pd.DataFrame:
        m = len(values)
        return pd.DataFrame(
            {
                "symbol": ["000001"] * m,
                "session": ["20250103"] * m,
                "open": np.full(m, 100.0),
                "high": np.full(m, 101.0),
                "low": np.full(m, 99.0),
                "close": np.full(m, 100.0),
                "volume": np.full(m, 10.0),
                "amount": np.full(m, 500.0),
                "체결강도": values,
            }
        )

    base = build_stom_rl_feature_frame(_frame(strengths))
    avg = base["trade_strength_avg_n"].to_numpy(dtype="float64")

    # Reference: explicit backward-only window mean over rows [max(0, T-N+1), T].
    clipped = np.clip(strengths, 0.0, 500.0)
    expected = np.array(
        [clipped[max(0, t - window + 1) : t + 1].mean() for t in range(n)]
    )
    np.testing.assert_allclose(avg, expected)

    # Leakage guard: append extreme FUTURE rows; rows <= T must be byte-identical.
    future = np.concatenate([strengths, np.full(10, 9999.0)])
    extended = build_stom_rl_feature_frame(_frame(future))
    np.testing.assert_allclose(
        extended["trade_strength_avg_n"].to_numpy(dtype="float64")[:n], avg
    )

    # Modifying ONLY a future row must not change any row at or before T.
    mutated = strengths.copy()
    mutated_future = np.concatenate([mutated, np.full(5, 0.0)])
    mutated_future[n + 2] = 12345.0  # a far-future spike
    mutated_frame = build_stom_rl_feature_frame(_frame(mutated_future))
    np.testing.assert_allclose(
        mutated_frame["trade_strength_avg_n"].to_numpy(dtype="float64")[:n], avg
    )


def test_export_stom_rl_features_populates_stage_c_columns(tmp_path: Path):
    """The real export path emits the 4 new columns, populated and finite."""

    db_path = tmp_path / "fixture.db"
    rows = [
        _fixture_row(20221212090005 + i, close=9260.0 + i, buy=10.0 + i, sell=3.0 + i, amount=100.0 + i)
        for i in range(8)
    ]
    _make_fixture_db(db_path, rows)

    report = export_stom_rl_features(
        db_path=db_path,
        output_dir=tmp_path / "out",
        table="000020",
        session="20221212",
        time_start="090000",
        time_end="093000",
        max_rows=5000,
    )

    frame = pd.read_csv(Path(report["csv_path"]), encoding="utf-8-sig")
    for new_col in (
        "change_rate",
        "market_cap",
        "high_low_mid_change_rate",
        "trade_strength_avg_n",
    ):
        assert new_col in frame.columns
        assert np.isfinite(frame[new_col].to_numpy(dtype="float64")).all()

    # 등락율=1.25, 고저평균대비등락율=-0.5, 시가총액=45000 in every fixture row.
    np.testing.assert_allclose(frame["change_rate"].to_numpy(), 1.25)
    np.testing.assert_allclose(frame["high_low_mid_change_rate"].to_numpy(), -0.5)
    np.testing.assert_allclose(frame["market_cap"].to_numpy(), np.log1p(45000.0))
    # Constant strength=200 fixture -> trailing mean is 200 everywhere.
    np.testing.assert_allclose(frame["trade_strength_avg_n"].to_numpy(), 200.0)
    assert report["canonical_features"] == list(STOM_RL_CANONICAL_FEATURES)


# ---------------------------------------------------------------------------
# Stage 2 — net-new RL resampler + causal trend features.
# Test ordering note (plan R7): V-RESAMPLE-SEMANTICS and V-NONDEGEN are
# feature-integrity gates that MUST hold before any alpha/shuffle use; they
# assert loudly so a silent-zero / mis-aggregated feature can never reach the
# alpha verdict.
# ---------------------------------------------------------------------------


def _rl_source_minute_frame() -> pd.DataFrame:
    """A synthetic RL *source* frame: 1 symbol/session, two 1-min buckets of
    per-second rows, carrying the DB-named source columns the resampler keys on.

    Bucket A = 09:00:00..09:00:02 (3 seconds), bucket B = 09:01:00..09:01:01
    (2 seconds).  Flow columns vary per second (so SUM != LAST); book/rate
    columns step DOWN within each bucket so the last-second value is distinct
    from first/mean (so LAST is verifiable).
    """

    ts = [
        pd.Timestamp("2025-01-03 09:00:00"),
        pd.Timestamp("2025-01-03 09:00:01"),
        pd.Timestamp("2025-01-03 09:00:02"),
        pd.Timestamp("2025-01-03 09:01:00"),
        pd.Timestamp("2025-01-03 09:01:01"),
    ]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "symbol": ["000001"] * 5,
            "session": ["20250103"] * 5,
            "open": [100.0, 101.0, 102.0, 110.0, 111.0],
            "high": [105.0, 106.0, 107.0, 115.0, 116.0],
            "low": [99.0, 98.0, 97.0, 108.0, 107.0],
            "close": [101.0, 102.0, 103.0, 111.0, 112.0],
            "초당매수수량": [10.0, 20.0, 30.0, 40.0, 50.0],
            "초당매도수량": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": [11.0, 22.0, 33.0, 44.0, 55.0],
            "amount": [100.0, 200.0, 300.0, 400.0, 500.0],
            "매수총잔량": [80.0, 70.0, 60.0, 50.0, 40.0],
            "매도총잔량": [20.0, 25.0, 30.0, 35.0, 40.0],
            "매수호가1": [99.0, 98.0, 97.0, 107.0, 106.0],
            "매도호가1": [101.0, 102.0, 103.0, 113.0, 114.0],
            "등락율": [1.0, 1.5, 2.0, 2.5, 3.0],
            "회전율": [0.10, 0.11, 0.12, 0.13, 0.14],
            "시가총액": [45000.0, 45010.0, 45020.0, 45030.0, 45040.0],
            "고저평균대비등락율": [-1.0, -0.5, 0.0, 0.5, 1.0],
            "체결강도": [200.0, 210.0, 220.0, 230.0, 240.0],
        }
    )


def test_v_resample_semantics_flow_sum_book_rate_last():
    """V-RESAMPLE-SEMANTICS: on a synthetic minute the net-new resampler sums
    flow columns (incl. amount, per Stage-1 §2), snapshots book/rate columns to
    the LAST second, keeps OHLC=first/max/min/last, and preserves ALL inputs."""

    src = _rl_source_minute_frame()
    out = resample_stom_rl_source_frame(src, freq="1min")

    # Two 1-min buckets, labeled at bucket START (floor("min")).
    assert len(out) == 2
    assert list(out["timestamp"]) == [
        pd.Timestamp("2025-01-03 09:00:00"),
        pd.Timestamp("2025-01-03 09:01:00"),
    ]

    # ALL source inputs survive the resample (no silent drop, R1).
    for col in src.columns:
        assert col in out.columns

    bucket_a = out.iloc[0]
    bucket_b = out.iloc[1]

    # OHLC: first / max / min / last over the bucket.
    assert bucket_a["open"] == 100.0  # first
    assert bucket_a["high"] == 107.0  # max
    assert bucket_a["low"] == 97.0  # min
    assert bucket_a["close"] == 103.0  # last

    # Flow -> SUM == hand-sum of the per-second values.
    assert bucket_a["초당매수수량"] == 10.0 + 20.0 + 30.0
    assert bucket_a["초당매도수량"] == 1.0 + 2.0 + 3.0
    assert bucket_a["volume"] == 11.0 + 22.0 + 33.0
    # CRITICAL Stage-1 branch: amount == SUM (per-second 초당거래대금), NOT last.
    assert bucket_a["amount"] == 100.0 + 200.0 + 300.0
    assert bucket_b["amount"] == 400.0 + 500.0

    # Book + rate/snapshot -> LAST second's value in the bucket.
    assert bucket_a["매수총잔량"] == 60.0
    assert bucket_a["매도총잔량"] == 30.0
    assert bucket_a["매수호가1"] == 97.0
    assert bucket_a["매도호가1"] == 103.0
    assert bucket_a["등락율"] == 2.0
    assert bucket_a["회전율"] == 0.12
    assert bucket_a["시가총액"] == 45020.0
    assert bucket_a["고저평균대비등락율"] == 0.0
    assert bucket_a["체결강도"] == 220.0


def test_v_resample_freq_1s_is_identity():
    """freq='1s' returns the frame unchanged so the 1s path stays byte-identical."""

    src = _rl_source_minute_frame()
    out = resample_stom_rl_source_frame(src, freq="1s")
    pd.testing.assert_frame_equal(out, src)


def test_v_nondegen_one_minute_panel_features_have_variance():
    """V-NONDEGEN: a 1-min panel's flow/book/rate + trend features have NON-ZERO
    variance.  All-zero would mean the resample silently dropped source columns
    (R1/R5) -> manufactured false null -> FAIL LOUDLY here."""

    # Many per-second rows across several minutes so each 1-min bucket is dense
    # and the trend features have multiple bars to vary over.
    base = pd.Timestamp("2025-01-03 09:00:00")
    n = 300  # 5 minutes of per-second rows
    rng = np.arange(n, dtype="float64")
    src = pd.DataFrame(
        {
            "timestamp": [base + pd.Timedelta(seconds=int(i)) for i in range(n)],
            "symbol": ["000001"] * n,
            "session": ["20250103"] * n,
            "open": 100.0 + rng * 0.1,
            "high": 101.0 + rng * 0.1,
            "low": 99.0 + rng * 0.1,
            "close": 100.0 + np.sin(rng / 5.0) * 3.0 + rng * 0.05,
            "초당매수수량": 10.0 + (rng % 7),
            "초당매도수량": 3.0 + (rng % 5),
            "volume": 13.0 + (rng % 7) + (rng % 5),
            "amount": 100.0 + (rng % 11) * 10.0,
            "매수총잔량": 80.0 + (rng % 13),
            "매도총잔량": 20.0 + (rng % 9),
            "매수호가1": 99.0 + rng * 0.1,
            "매도호가1": 101.0 + rng * 0.1,
            "등락율": np.sin(rng / 4.0) * 2.0,
            "회전율": 0.10 + (rng % 3) * 0.01,
            "시가총액": 45000.0 + rng,
            "고저평균대비등락율": np.cos(rng / 6.0),
            "체결강도": 150.0 + (rng % 17) * 5.0,
        }
    )

    resampled = resample_stom_rl_source_frame(src, freq="1min")
    features = build_stom_rl_feature_frame(resampled)

    # The resampled panel must have multiple 1-min bars (else variance is vacuous).
    assert len(features) >= 4

    must_vary = [
        "trade_strength",
        "bid_ask_imbalance",
        "change_rate",
        "amount",
        "volume",
        "moving_average_n",
        "volatility_n",
        "amount_slope_n",
        "change_rate_slope_n",
    ]
    for col in must_vary:
        variance = float(features[col].var())
        assert variance > 0.0, f"feature {col!r} is degenerate (zero variance) on the 1-min panel"


def test_v_freq_no_lookahead_bar_carries_no_next_bar_value():
    """V-FREQ: a 1-min bar T carries NO value from bar T+1.  A synthetic monotone
    per-second series resampled to 1-min must label at the bucket start and the
    last-second (LAST) columns of bar T must equal bar T's own last second, never
    bar T+1's."""

    base = pd.Timestamp("2025-01-03 09:00:00")
    rows = []
    # Two minutes, monotone-increasing 등락율 across the whole series.
    for minute in range(2):
        for sec in range(3):
            t = base + pd.Timedelta(minutes=minute, seconds=sec)
            val = minute * 100.0 + sec * 10.0  # strictly increasing
            rows.append((t, val))
    src = pd.DataFrame(
        {
            "timestamp": [r[0] for r in rows],
            "symbol": ["000001"] * len(rows),
            "session": ["20250103"] * len(rows),
            "open": [100.0] * len(rows),
            "high": [101.0] * len(rows),
            "low": [99.0] * len(rows),
            "close": [100.0] * len(rows),
            "amount": [r[1] for r in rows],
            "등락율": [r[1] for r in rows],
        }
    )

    out = resample_stom_rl_source_frame(src, freq="1min")
    assert list(out["timestamp"]) == [base, base + pd.Timedelta(minutes=1)]

    # Bar T=0 (09:00) LAST 등락율 is its OWN last second (sec=2 -> 20.0), NOT any
    # value from bar T=1 (09:01, which starts at 100.0).  No look-ahead.
    assert out.iloc[0]["등락율"] == 20.0
    assert out.iloc[1]["등락율"] == 120.0
    # The bucket-start label coheres with the grid-agnostic T+1 fill: a decision
    # at bar T fills at T+1 = the NEXT 1-min bar, so bar T must not embed T+1.
    assert out.iloc[0]["timestamp"] < out.iloc[1]["timestamp"]


@pytest.mark.parametrize(
    "feature,source_col,source_values",
    [
        ("moving_average_n", "close", None),
        ("volatility_n", "등락율", None),
        ("amount_slope_n", "amount", None),
        ("change_rate_slope_n", "등락율", None),
    ],
)
def test_v_causal_trend_feature_is_strictly_trailing(feature, source_col, source_values):
    """V-CAUSAL: each trend feature at row T is UNCHANGED when future bars are
    appended or a far-future bar is mutated (row T uses only bars <= T)."""

    n = 24
    driver = (np.arange(n, dtype="float64") % 6) * 3.0 + 1.0 if source_values is None else source_values

    def _frame(values: np.ndarray) -> pd.DataFrame:
        m = len(values)
        data = {
            "symbol": ["000001"] * m,
            "session": ["20250103"] * m,
            "open": np.full(m, 100.0),
            "high": np.full(m, 101.0),
            "low": np.full(m, 99.0),
            "close": np.full(m, 100.0),
            "volume": np.full(m, 10.0),
            "amount": np.full(m, 500.0),
            "체결강도": np.full(m, 200.0),
            "등락율": np.zeros(m),
        }
        data[source_col] = values
        return pd.DataFrame(data)

    base = build_stom_rl_feature_frame(_frame(driver))
    base_vals = base[feature].to_numpy(dtype="float64")

    # Append extreme FUTURE bars; rows <= T must be byte-identical.
    extended = np.concatenate([driver, np.full(8, 9999.0)])
    ext_vals = build_stom_rl_feature_frame(_frame(extended))[feature].to_numpy(dtype="float64")
    np.testing.assert_allclose(ext_vals[:n], base_vals)

    # Mutate ONLY a far-future bar; no row at or before T may change.
    mutated = np.concatenate([driver, np.full(5, 0.0)])
    mutated[n + 2] = -88888.0
    mut_vals = build_stom_rl_feature_frame(_frame(mutated))[feature].to_numpy(dtype="float64")
    np.testing.assert_allclose(mut_vals[:n], base_vals)


def test_trend_slope_matches_closed_form_trailing_ols():
    """``amount_slope_n`` equals the hand-computed trailing-OLS slope
    cov(x,y)/var(x) over the last N bars (the Stage-1 LOCKED formula)."""

    window = STOM_RL_TREND_WINDOW
    n = 15
    amounts = np.arange(n, dtype="float64") ** 1.5 + 10.0
    frame = pd.DataFrame(
        {
            "symbol": ["000001"] * n,
            "session": ["20250103"] * n,
            "open": np.full(n, 100.0),
            "high": np.full(n, 101.0),
            "low": np.full(n, 99.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 10.0),
            "amount": amounts,
            "체결강도": np.full(n, 200.0),
            "등락율": np.zeros(n),
        }
    )
    out = build_stom_rl_feature_frame(frame)
    got = out["amount_slope_n"].to_numpy(dtype="float64")

    def _ols(y: np.ndarray) -> float:
        k = y.size
        if k < 2:
            return 0.0  # min_periods=2 -> filled to 0.0 by build frame
        x = np.arange(k, dtype="float64")
        xm, ym = x.mean(), y.mean()
        var_x = ((x - xm) ** 2).sum()
        return float(((x - xm) * (y - ym)).sum() / var_x)

    expected = np.array(
        [_ols(amounts[max(0, t - window + 1) : t + 1]) for t in range(n)]
    )
    # Row 0 has a single point -> NaN -> filled to 0.0 by build frame.
    expected[0] = 0.0
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-9)


def test_volatility_uses_locked_population_std_ddof():
    """``volatility_n`` is the trailing population std (ddof=0, Stage-1 LOCKED) of
    change_rate over the last N bars."""

    assert STOM_RL_VOLATILITY_DDOF == 0
    window = STOM_RL_TREND_WINDOW
    n = 14
    rates = np.sin(np.arange(n, dtype="float64") / 2.0) * 2.0
    frame = pd.DataFrame(
        {
            "symbol": ["000001"] * n,
            "session": ["20250103"] * n,
            "open": np.full(n, 100.0),
            "high": np.full(n, 101.0),
            "low": np.full(n, 99.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 10.0),
            "amount": np.full(n, 500.0),
            "체결강도": np.full(n, 200.0),
            "등락율": rates,
        }
    )
    out = build_stom_rl_feature_frame(frame)
    got = out["volatility_n"].to_numpy(dtype="float64")

    expected = np.array(
        [
            float(np.std(rates[max(0, t - window + 1) : t + 1], ddof=0))
            for t in range(n)
        ]
    )
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-9)


# ---------------------------------------------------------------------------
# Story B1 — session-bar ("daily proxy") resample mode.
#
# freq="session" collapses ALL rows of one (symbol, session) into ONE bar using
# the SAME LOCKED per-column aggregation as the 1-min path (OHLC=first/max/min/
# last, flow/amount=SUM, book/rate=LAST), timestamps the bar at the session
# date, and (via build_stom_rl_feature_frame trend_group_keys) computes the
# causal trend features ACROSS the per-symbol session series with no look-ahead.
# This is a CAVEATED PROXY (morning-30min, selection-biased), NOT a daily bar.
# ---------------------------------------------------------------------------
def _rl_source_two_session_frame() -> pd.DataFrame:
    """One symbol, TWO sessions, several per-second rows each.

    Session A = 20250103 (3 seconds), session B = 20250106 (2 seconds).  Flow
    columns vary per second (SUM != LAST); book/rate columns step within each
    session so LAST is distinguishable from first/mean.
    """

    return pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2025-01-03 09:00:00"),
                pd.Timestamp("2025-01-03 09:00:01"),
                pd.Timestamp("2025-01-03 09:00:02"),
                pd.Timestamp("2025-01-06 09:00:00"),
                pd.Timestamp("2025-01-06 09:00:01"),
            ],
            "symbol": ["000001"] * 5,
            "session": ["20250103", "20250103", "20250103", "20250106", "20250106"],
            "open": [100.0, 101.0, 102.0, 110.0, 111.0],
            "high": [105.0, 106.0, 107.0, 115.0, 116.0],
            "low": [99.0, 98.0, 97.0, 108.0, 107.0],
            "close": [101.0, 102.0, 103.0, 111.0, 112.0],
            "초당매수수량": [10.0, 20.0, 30.0, 40.0, 50.0],
            "초당매도수량": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": [11.0, 22.0, 33.0, 44.0, 55.0],
            "amount": [100.0, 200.0, 300.0, 400.0, 500.0],
            "매수총잔량": [80.0, 70.0, 60.0, 50.0, 40.0],
            "매도총잔량": [20.0, 25.0, 30.0, 35.0, 40.0],
            "매수호가1": [99.0, 98.0, 97.0, 107.0, 106.0],
            "매도호가1": [101.0, 102.0, 103.0, 113.0, 114.0],
            "등락율": [1.0, 1.5, 2.0, 2.5, 3.0],
            "회전율": [0.10, 0.11, 0.12, 0.13, 0.14],
            "시가총액": [45000.0, 45010.0, 45020.0, 45030.0, 45040.0],
            "고저평균대비등락율": [-1.0, -0.5, 0.0, 0.5, 1.0],
            "체결강도": [200.0, 210.0, 220.0, 230.0, 240.0],
        }
    )


def test_v_session_resample_one_bar_per_symbol_session():
    """V-SESSION-BAR: freq='session' produces exactly ONE bar per (symbol,
    session), timestamped at the session date, with the LOCKED per-column agg."""

    src = _rl_source_two_session_frame()
    out = resample_stom_rl_source_frame(src, freq="session")

    # Exactly one bar per session (2 sessions for 1 symbol).
    assert len(out) == 2
    assert list(out["session"]) == ["20250103", "20250106"]
    # Bar timestamp = the session DATE (midnight), so cross-session bars of
    # different symbols align on a shared session-date axis.
    assert list(out["timestamp"]) == [
        pd.Timestamp("2025-01-03 00:00:00"),
        pd.Timestamp("2025-01-06 00:00:00"),
    ]

    # ALL source inputs survive (no silent drop -> no manufactured null).
    for col in src.columns:
        assert col in out.columns

    sess_a = out.iloc[0]
    sess_b = out.iloc[1]

    # OHLC over the WHOLE session: first / max / min / last.
    assert sess_a["open"] == 100.0
    assert sess_a["high"] == 107.0
    assert sess_a["low"] == 97.0
    assert sess_a["close"] == 103.0
    assert sess_b["open"] == 110.0
    assert sess_b["close"] == 112.0

    # Flow + amount -> SUM over the entire session (Stage-1 LOCKED).
    assert sess_a["초당매수수량"] == 10.0 + 20.0 + 30.0
    assert sess_a["초당매도수량"] == 1.0 + 2.0 + 3.0
    assert sess_a["volume"] == 11.0 + 22.0 + 33.0
    assert sess_a["amount"] == 100.0 + 200.0 + 300.0
    assert sess_b["amount"] == 400.0 + 500.0

    # Book + rate/snapshot -> LAST second of the session.
    assert sess_a["매수총잔량"] == 60.0
    assert sess_a["매도총잔량"] == 30.0
    assert sess_a["매수호가1"] == 97.0
    assert sess_a["매도호가1"] == 103.0
    assert sess_a["등락율"] == 2.0
    assert sess_a["회전율"] == 0.12
    assert sess_a["시가총액"] == 45020.0
    assert sess_a["고저평균대비등락율"] == 0.0
    assert sess_a["체결강도"] == 220.0


def test_v_session_resample_cross_symbol_dates_align():
    """V-SESSION-PANEL: two symbols sharing a session date collapse to bars on
    the SAME timestamp, so a cross-session panel can key on session-date."""

    a = _rl_source_two_session_frame()
    b = _rl_source_two_session_frame().assign(symbol="000002")
    src = pd.concat([a, b], ignore_index=True)
    out = resample_stom_rl_source_frame(src, freq="session")

    assert len(out) == 4  # 2 symbols x 2 sessions
    # Both symbols' 20250103 bar share the identical session-date timestamp.
    jan3 = out[out["timestamp"] == pd.Timestamp("2025-01-03 00:00:00")]
    assert set(jan3["symbol"]) == {"000001", "000002"}


def test_v_session_trend_features_are_causal_across_sessions():
    """V-SESSION-CAUSAL: with trend_group_keys=['symbol'] the trailing trend
    features compute ACROSS the per-symbol session series and use ONLY sessions
    <= T (no look-ahead): row T is unchanged when a far-future session is added.

    This is also why the session path needs trend_group_keys=['symbol']: under
    the default [symbol, session] grouping each one-row session is a length-1
    window and every trend feature would collapse to a constant.
    """

    sessions = [f"2025010{d}" for d in range(1, 7)]  # 6 sessions
    closes = [100.0, 102.0, 101.0, 105.0, 110.0, 108.0]

    def _session_bars(n: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": [pd.Timestamp(f"{s[:4]}-{s[4:6]}-{s[6:]}") for s in sessions[:n]],
                "symbol": ["000001"] * n,
                "session": sessions[:n],
                "open": closes[:n],
                "high": [c + 2 for c in closes[:n]],
                "low": [c - 2 for c in closes[:n]],
                "close": closes[:n],
                "volume": [10.0] * n,
                "amount": [500.0 + 10 * i for i in range(n)],
                "체결강도": [200.0] * n,
                "등락율": [float(i) for i in range(n)],
            }
        )

    full = build_stom_rl_feature_frame(_session_bars(6), trend_group_keys=["symbol"])
    short = build_stom_rl_feature_frame(_session_bars(4), trend_group_keys=["symbol"])

    # Trend features are non-degenerate across sessions (would be all-equal under
    # the default per-(symbol,session) length-1 grouping).
    assert full["moving_average_n"].nunique() > 1
    assert full["amount_slope_n"].nunique() > 1

    # Causal: the first 4 session rows are byte-identical whether or not the 2
    # later sessions exist -> row T sees only sessions <= T.
    for col in (
        "moving_average_n",
        "volatility_n",
        "amount_slope_n",
        "change_rate_slope_n",
        "amount_delta",
    ):
        np.testing.assert_allclose(
            full[col].to_numpy()[:4], short[col].to_numpy(), rtol=1e-9, atol=1e-9
        )


def test_v_session_resample_default_grouping_collapses_trend():
    """The default [symbol, session] grouping makes per-session trend features
    degenerate (length-1 windows) — documenting WHY freq='session' must pass
    trend_group_keys=['symbol'] (guards against a silent manufactured null)."""

    sessions = [f"2025010{d}" for d in range(1, 6)]
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(f"{s[:4]}-{s[4:6]}-{s[6:]}") for s in sessions],
            "symbol": ["000001"] * 5,
            "session": sessions,
            "open": [100.0, 102.0, 101.0, 105.0, 110.0],
            "high": [106.0] * 5,
            "low": [96.0] * 5,
            "close": [100.0, 102.0, 101.0, 105.0, 110.0],
            "volume": [10.0] * 5,
            "amount": [500.0, 510.0, 520.0, 530.0, 540.0],
            "체결강도": [200.0] * 5,
            "등락율": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    # Default grouping: each (symbol, session) is one row -> slope NaN->0, MA=close.
    default = build_stom_rl_feature_frame(bars)
    assert (default["amount_slope_n"] == 0.0).all()
    np.testing.assert_allclose(
        default["moving_average_n"].to_numpy(), bars["close"].to_numpy()
    )
