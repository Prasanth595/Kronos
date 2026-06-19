import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "finetune_csv"))

from stom_tick_dataset import (  # noqa: E402
    GroupedKlineDataset,
    export_stom_tick_db_to_csv,
    inspect_stom_tick_db,
    read_stom_table_as_kline,
)


def _create_stom_db(path: Path, rows_per_session: int = 8):
    conn = sqlite3.connect(path)
    try:
        for symbol, base_price in [("000001", 1000), ("000002", 2000)]:
            conn.execute(
                f'''
                CREATE TABLE "{symbol}" (
                    "index" INTEGER,
                    "현재가" REAL,
                    "시가" REAL,
                    "고가" REAL,
                    "저가" REAL,
                    "초당매수수량" REAL,
                    "초당매도수량" REAL,
                    "초당거래대금" REAL
                )
                '''
            )
            for day in [datetime(2026, 1, 2, 9, 0, 0), datetime(2026, 1, 3, 9, 0, 0)]:
                for i in range(rows_per_session):
                    ts = int((day + timedelta(seconds=i)).strftime("%Y%m%d%H%M%S"))
                    close = base_price + i
                    buy_qty = i + 1
                    sell_qty = i + 2
                    volume = buy_qty + sell_qty
                    conn.execute(
                        f'INSERT INTO "{symbol}" VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (
                            ts,
                            close,
                            base_price,
                            close + 1,
                            base_price - 1,
                            buy_qty,
                            sell_qty,
                            close * volume,
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def test_inspect_stom_tick_db_detects_trainable_groups(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    _create_stom_db(db_path)

    summary = inspect_stom_tick_db(
        db_path,
        max_tables=0,
        lookback_window=3,
        predict_window=2,
        price_mode="close_only",
    )

    assert summary["table_count"] == 2
    assert summary["compatible_table_count"] == 2
    assert summary["eligible_group_count"] == 4
    assert summary["trainable"] is True


def test_export_stom_tick_db_to_grouped_kronos_csv(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    csv_path = tmp_path / "stom_1tick_kline.csv"
    _create_stom_db(db_path)

    report = export_stom_tick_db_to_csv(
        db_path,
        csv_path,
        max_tables=0,
        lookback_window=3,
        predict_window=2,
        price_mode="close_only",
    )
    df = pd.read_csv(csv_path)

    assert report["trainable_csv_created"] is True
    assert set(["symbol", "session", "timestamps", "open", "high", "low", "close", "volume", "amount"]).issubset(df.columns)
    assert len(df[["symbol", "session"]].drop_duplicates()) == 4
    first = df.iloc[0]
    assert first["open"] == first["high"] == first["low"] == first["close"]
    assert first["volume"] == 3


def test_export_can_clip_each_group_to_bounded_contiguous_rows(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    csv_path = tmp_path / "stom_1tick_kline_clipped.csv"
    _create_stom_db(db_path, rows_per_session=10)

    report = export_stom_tick_db_to_csv(
        db_path,
        csv_path,
        max_tables=0,
        lookback_window=3,
        predict_window=2,
        price_mode="close_only",
        max_rows_per_group=6,
    )
    df = pd.read_csv(csv_path)

    assert report["trainable_csv_created"] is True
    assert report["clipped_groups"] == 4
    assert report["max_rows_per_group"] == 6
    assert df.groupby(["symbol", "session"]).size().tolist() == [6, 6, 6, 6]


def test_grouped_kline_dataset_keeps_windows_inside_symbol_session(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    csv_path = tmp_path / "stom_1tick_kline.csv"
    _create_stom_db(db_path)
    export_stom_tick_db_to_csv(
        db_path,
        csv_path,
        max_tables=0,
        lookback_window=3,
        predict_window=2,
        price_mode="close_only",
    )

    dataset = GroupedKlineDataset(
        csv_path,
        data_type="train",
        lookback_window=3,
        predict_window=2,
        train_ratio=1.0,
        val_ratio=0.0,
        test_ratio=0.0,
        normalize_using="lookback",
    )

    assert len(dataset) == 12
    assert dataset.groups[0]["key"][0].startswith("00000")
    x, x_stamp = dataset.get_numpy(0)
    assert tuple(x.shape) == (6, 6)
    assert tuple(x_stamp.shape) == (6, 5)
    assert np.allclose(x[:3].mean(axis=0), np.zeros(6), atol=1e-5)

    for idx in range(len(dataset)):
        metadata = dataset.sample_metadata(idx)
        assert metadata["start_timestamp"][:10] == metadata["end_timestamp"][:10]


def test_read_stom_table_as_kline_uses_query_only_connection(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    _create_stom_db(db_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    try:
        frame, mapping = read_stom_table_as_kline(conn, "000001", price_mode="close_only")
    finally:
        conn.close()

    assert mapping["close"] == "현재가"
    assert frame["symbol"].unique().tolist() == ["000001"]
    assert frame[["open", "high", "low", "close"]].nunique(axis=1).eq(1).all()


def test_read_stom_table_as_kline_can_filter_session_range(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    _create_stom_db(db_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    try:
        frame, _ = read_stom_table_as_kline(
            conn,
            "000001",
            price_mode="close_only",
            session_start="20260103",
            session_end="20260103",
        )
    finally:
        conn.close()

    assert frame["session"].unique().tolist() == ["20260103"]
