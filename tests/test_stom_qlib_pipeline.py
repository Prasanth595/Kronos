import json
import pickle
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "finetune"))
sys.path.insert(0, str(REPO_ROOT / "webui"))

from qlib_stom_pipeline import (  # noqa: E402
    StomQlibExportConfig,
    check_qlib_environment,
    export_stom_to_qlib,
    run_dump_bin_from_report,
    run_score_backtest,
    smoke_qlib_provider,
)
import stom_dashboard  # noqa: E402


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
            for day in [
                datetime(2026, 1, 2, 9, 0, 0),
                datetime(2026, 1, 3, 9, 0, 0),
                datetime(2026, 1, 4, 9, 0, 0),
            ]:
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
                            close - 1,
                            close + 1,
                            close - 2,
                            buy_qty,
                            sell_qty,
                            close * volume,
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def test_export_stom_to_qlib_pilot_outputs_dump_ready_csv_and_pickles(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    out_dir = tmp_path / "qlib_export"
    _create_stom_db(db_path)

    report = export_stom_to_qlib(
        StomQlibExportConfig(
            db_path=str(db_path),
            output_dir=str(out_dir),
            lookback_window=3,
            predict_window=2,
            price_mode="close_only",
            train_ratio=0.5,
            val_ratio=0.25,
            test_ratio=0.25,
        )
    )

    assert report["exported_group_count"] == 6
    assert report["split_strategy"] == "session"
    assert report["split_counts"]["train"]["groups"] == 2
    assert set(report["split_sessions"]["train"]).isdisjoint(report["split_sessions"]["val"])
    assert set(report["split_sessions"]["train"]).isdisjoint(report["split_sessions"]["test"])
    assert (out_dir / "stom_qlib_export_report.json").exists()
    dump_command = (out_dir / "meta" / "qlib_dump_bin_command.txt").read_text(encoding="utf-8")
    assert dump_command.startswith("python scripts/dump_bin.py dump_all")
    assert "--freq 1s" in dump_command
    csv_files = sorted((out_dir / "qlib_csv").glob("*.csv"))
    assert len(csv_files) == 6
    sample_csv = pd.read_csv(csv_files[0])
    assert {"symbol", "date", "open", "high", "low", "close", "volume", "amount", "money", "factor"}.issubset(
        sample_csv.columns
    )

    with (out_dir / "processed_datasets" / "train_data.pkl").open("rb") as f:
        train_data = pickle.load(f)
    first_frame = next(iter(train_data.values()))
    assert list(first_frame.columns) == ["open", "high", "low", "close", "vol", "amt"]
    assert first_frame.index.name == "datetime"


def test_export_regularizes_1s_grid_and_keeps_sessions_out_of_multiple_splits(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    out_dir = tmp_path / "qlib_export_grid"
    conn = sqlite3.connect(db_path)
    try:
        for symbol, base_price in [("000001", 1000), ("000002", 2000)]:
            conn.execute(
                f'''
                CREATE TABLE "{symbol}" (
                    "index" INTEGER,
                    "현재가" REAL,
                    "초당매수수량" REAL,
                    "초당매도수량" REAL,
                    "초당거래대금" REAL
                )
                '''
            )
            for day in [
                datetime(2026, 1, 2, 9, 0, 0),
                datetime(2026, 1, 3, 9, 0, 0),
                datetime(2026, 1, 4, 9, 0, 0),
            ]:
                for offset in [0, 2, 5, 6]:
                    ts = int((day + timedelta(seconds=offset)).strftime("%Y%m%d%H%M%S"))
                    close = base_price + offset
                    conn.execute(
                        f'INSERT INTO "{symbol}" VALUES (?, ?, ?, ?, ?)',
                        (ts, close, 1, 2, close * 3),
                    )
        conn.commit()
    finally:
        conn.close()

    report = export_stom_to_qlib(
        StomQlibExportConfig(
            db_path=str(db_path),
            output_dir=str(out_dir),
            lookback_window=2,
            predict_window=2,
            horizon_seconds=2,
            price_mode="close_only",
            time_start="090000",
            time_end="090006",
            regularize_1s=True,
            train_ratio=0.34,
            val_ratio=0.33,
            test_ratio=0.33,
        )
    )

    assert report["config"]["effective_predict_window"] == 2
    assert report["grid_summary"]["regularized_groups"] == 6
    assert report["grid_summary"]["inserted_rows"] == 18
    assert set(report["split_sessions"]["train"]).isdisjoint(report["split_sessions"]["val"])
    assert set(report["split_sessions"]["val"]).isdisjoint(report["split_sessions"]["test"])

    sample_csv = pd.read_csv(sorted((out_dir / "qlib_csv").glob("*.csv"))[0])
    timestamps = pd.to_datetime(sample_csv["date"])
    assert timestamps.diff().dropna().dt.total_seconds().eq(1).all()
    filled_row = sample_csv.loc[sample_csv["date"].str.endswith("09:00:01")].iloc[0]
    assert filled_row["close"] == 1000
    assert filled_row["volume"] == 0
    assert filled_row["amount"] == 0


def test_export_stom_to_qlib_can_limit_session_range(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    out_dir = tmp_path / "qlib_export_2026_session"
    _create_stom_db(db_path)

    report = export_stom_to_qlib(
        StomQlibExportConfig(
            db_path=str(db_path),
            output_dir=str(out_dir),
            lookback_window=3,
            predict_window=2,
            price_mode="close_only",
            session_start="20260103",
            session_end="20260104",
            train_ratio=0.5,
            val_ratio=0.25,
            test_ratio=0.25,
        )
    )

    exported_sessions = {
        session
        for sessions in report["split_sessions"].values()
        for session in sessions
    }
    assert exported_sessions == {"20260103", "20260104"}
    assert report["config"]["session_start"] == "20260103"
    assert report["config"]["session_end"] == "20260104"


def test_score_backtest_and_dashboard_artifact_loader(tmp_path, monkeypatch):
    pred_csv = tmp_path / "predictions.csv"
    pred_csv.write_text(
        "window_id,symbol,session,asof_timestamp,target_timestamp,horizon_step,actual_close_t0,pred_close,actual_close,error,abs_error,pred_return_window,actual_return_window,direction_hit_window,mode\n"
        "0,000001,20260102,2026-01-02T09:05:00,2026-01-02T09:06:00,60,100,103,102,1,1,3.0,2.0,1,kronos\n"
        "1,000002,20260102,2026-01-02T09:05:00,2026-01-02T09:06:00,60,100,101,99,2,2,1.0,-1.0,0,kronos\n"
        "2,000003,20260102,2026-01-02T09:05:00,2026-01-02T09:06:00,60,100,104,103,1,1,4.0,3.0,1,kronos\n"
        "3,000001,20260103,2026-01-03T09:05:00,2026-01-03T09:06:00,60,100,99,98,1,1,-1.0,-2.0,1,kronos\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "backtests"

    result = run_score_backtest(pred_csv, out_dir, top_k=2, cost_bps=10, slippage_bps=5)

    assert result["metrics"]["period_count"] == 2
    assert result["metrics"]["trade_count"] == 3
    assert result["metrics"]["cost_bps"] == 10
    assert Path(result["artifact_paths"]["json"]).exists()

    monkeypatch.setattr(stom_dashboard, "QLIB_BACKTEST_DIRS", [out_dir])
    files = stom_dashboard.list_qlib_backtest_files()
    assert files[0]["name"].endswith(".json")
    artifact = stom_dashboard.load_qlib_backtest_artifact(files[0]["name"])
    chart = json.loads(stom_dashboard.qlib_backtest_chart_json(artifact))
    assert artifact["metrics"]["mode"] == "qlib_style_topk"
    assert chart["data"][0]["name"] == "Qlib Top-K equity"


def test_qlib_env_check_and_dump_bin_dry_run(tmp_path):
    report_path = tmp_path / "stom_qlib_export_report.json"
    csv_dir = tmp_path / "qlib_csv"
    csv_dir.mkdir()
    report_path.write_text(
        json.dumps(
            {
                "qlib_csv_dir": str(csv_dir),
                "output_dir": str(tmp_path / "export"),
                "config": {"freq": "1s"},
            }
        ),
        encoding="utf-8",
    )

    env = check_qlib_environment()
    assert "qlib_installed" in env
    assert env["recommended_install_command"] == "python -m pip install pyqlib"

    result = run_dump_bin_from_report(report_path, qlib_dir=tmp_path / "qlib_bin", execute=False, freq="1min")
    assert result["status"] == "dry_run"
    assert "--data_path" in result["command"]
    assert "--freq" in result["command"]
    assert result["command"][-1] == "1min"

    inferred = run_dump_bin_from_report(report_path, qlib_dir=tmp_path / "qlib_bin", execute=False)
    assert inferred["command"][-2:] == ["--freq", "1s"]


def test_provider_smoke_rejects_second_freq_before_importing_qlib(tmp_path):
    with pytest.raises(ValueError, match="1s"):
        smoke_qlib_provider(tmp_path, freq="1s")
