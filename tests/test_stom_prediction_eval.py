import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "finetune_csv"))

from stom_prediction_eval import evaluate_predictions, load_grouped_ohlcv  # noqa: E402
from stom_tick_dataset import export_stom_tick_db_to_csv  # noqa: E402


def _create_db(path: Path, rows: int = 12):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            '''
            CREATE TABLE "000001" (
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
        start = datetime(2026, 1, 2, 9, 0, 0)
        for i in range(rows):
            ts = int((start + timedelta(seconds=i)).strftime("%Y%m%d%H%M%S"))
            price = 1000 + i
            conn.execute(
                'INSERT INTO "000001" VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (ts, price, 1000, price, 1000, i + 1, i + 2, price * (i + 3)),
            )
        conn.commit()
    finally:
        conn.close()


def test_baseline_prediction_eval_writes_csv_and_metrics(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    data_path = tmp_path / "grouped.csv"
    output_path = tmp_path / "predictions.csv"
    _create_db(db_path)
    export_stom_tick_db_to_csv(
        db_path,
        data_path,
        max_tables=0,
        lookback_window=4,
        predict_window=3,
        price_mode="close_only",
    )

    metrics = evaluate_predictions(
        data_path=data_path,
        output_path=output_path,
        lookback_window=4,
        predict_window=3,
        max_windows=2,
        stride=2,
        mode="baseline",
    )
    out = pd.read_csv(output_path, dtype={"symbol": str, "session": str})

    assert output_path.exists()
    assert output_path.with_suffix(".metrics.json").exists()
    assert metrics["windows"] == 2
    assert len(out) == 6
    assert set(["pred_close", "actual_close", "pred_return_window", "actual_return_window"]).issubset(out.columns)
    assert out["symbol"].iloc[0] == "000001"


def test_load_grouped_ohlcv_preserves_symbol_string(tmp_path):
    csv_path = tmp_path / "grouped.csv"
    csv_path.write_text(
        "symbol,session,timestamps,open,high,low,close,volume,amount\n"
        "000001,20260102,2026-01-02 09:00:00,1,1,1,1,10,10\n",
        encoding="utf-8",
    )
    df = load_grouped_ohlcv(csv_path)
    assert df["symbol"].iloc[0] == "000001"
