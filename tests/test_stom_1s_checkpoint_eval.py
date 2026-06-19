import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = PROJECT_ROOT / "finetune"
if str(FINETUNE_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_DIR))

from evaluate_stom_1s_checkpoint import (  # noqa: E402
    load_pickle_dataset,
    persistence_predictions,
    random_direction_predictions,
    rows_from_predictions,
    select_aligned_windows,
    summarize_prediction_frame,
    write_prediction_artifacts,
)
from search_stom_1s_filters import (  # noqa: E402
    rolling_validate_filters,
    search_filters,
    write_filter_report,
    write_rolling_filter_report,
)


def _frame(rows: int = 12) -> pd.DataFrame:
    start = datetime(2026, 1, 2, 9, 0, 0)
    idx = [start + timedelta(seconds=i) for i in range(rows)]
    return pd.DataFrame(
        {
            "open": [100 + i for i in range(rows)],
            "high": [100 + i for i in range(rows)],
            "low": [100 + i for i in range(rows)],
            "close": [100 + i for i in range(rows)],
            "vol": [10 + i for i in range(rows)],
            "amt": [(100 + i) * (10 + i) for i in range(rows)],
        },
        index=pd.DatetimeIndex(idx, name="datetime"),
    )


def test_checkpoint_eval_baselines_write_dashboard_compatible_artifacts(tmp_path):
    dataset = tmp_path / "processed_datasets"
    dataset.mkdir()
    payload = {
        "KR000001_20260102": _frame(),
        "KR000002_20260102": _frame(),
    }
    with (dataset / "test_data.pkl").open("wb") as f:
        pickle.dump(payload, f)

    data = load_pickle_dataset(dataset)
    windows = select_aligned_windows(data, lookback_window=4, predict_window=3, max_symbols=2)
    persistence_df = rows_from_predictions(windows, persistence_predictions(windows), mode="persistence")
    random_df = rows_from_predictions(windows, random_direction_predictions(windows), mode="random")
    result = write_prediction_artifacts(
        {"persistence": persistence_df, "random": random_df},
        tmp_path / "predictions",
        "unit_eval",
        top_k=1,
    )

    assert len(windows) == 2
    assert persistence_df["symbol"].iloc[0] == "KR000001"
    assert persistence_df["horizon_step"].max() == 3
    assert summarize_prediction_frame(persistence_df)["windows"] == 2
    assert Path(result["files"]["persistence"]).exists()
    assert Path(result["comparison_path"]).exists()
    assert result["metrics"]["random"]["topk"]["k"] == 1
    assert "history_mean_amount" in persistence_df.columns
    assert "pred_path_consistency" in persistence_df.columns


def test_filter_search_reports_best_filter_from_prediction_csv(tmp_path):
    rows = []
    for idx in range(6):
        for step in range(1, 4):
            rows.append(
                {
                    "window_id": idx,
                    "symbol": f"KR{idx:06d}",
                    "session": "20260102",
                    "asof_timestamp": "2026-01-02T09:05:00" if idx < 3 else "2026-01-03T09:05:00",
                    "target_timestamp": f"2026-01-02T09:05:{step:02d}",
                    "horizon_step": step,
                    "actual_close_t0": 100,
                    "pred_close": 101 + idx,
                    "actual_close": 100 + idx,
                    "error": 1,
                    "abs_error": 1,
                    "pred_return_window": 0.2 if idx % 2 == 0 else -0.1,
                    "actual_return_window": 0.4 if idx % 2 == 0 else -0.2,
                    "direction_hit_window": 1,
                    "pred_path_consistency": 1.0 if idx % 2 == 0 else 0.4,
                    "pred_range_pct": 0.05,
                    "history_mean_amount": 1000 + idx * 100,
                    "history_volatility_pct": 0.05,
                    "mode": "kronos",
                }
            )
    csv_path = tmp_path / "pred.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    result = search_filters(csv_path, top_k=2, min_trades=1, min_periods=1, min_coverage=0.1)
    result = write_filter_report(result, tmp_path, "unit")

    assert result["best_filter"]["trade_count"] >= 1
    assert "filter_search.json" in result["artifact_paths"]["json"]
    assert Path(result["artifact_paths"]["csv"]).exists()


def test_rolling_filter_validation_uses_train_periods_then_tests_forward(tmp_path):
    rows = []
    window_id = 0
    for period in range(8):
        asof = datetime(2026, 1, 2, 9, 5, 0) + timedelta(minutes=period)
        for symbol_idx in range(4):
            pred_return = 0.2 if symbol_idx < 2 else -0.1
            actual_return = 0.3 if (period + symbol_idx) % 3 != 0 else -0.2
            for step in range(1, 4):
                rows.append(
                    {
                        "window_id": window_id,
                        "symbol": f"KR{symbol_idx:06d}",
                        "session": "20260102",
                        "asof_timestamp": asof.isoformat(),
                        "target_timestamp": (asof + timedelta(seconds=step)).isoformat(),
                        "horizon_step": step,
                        "actual_close_t0": 100,
                        "pred_close": 100 + pred_return,
                        "actual_close": 100 + actual_return,
                        "error": 0,
                        "abs_error": 0,
                        "pred_return_window": pred_return,
                        "actual_return_window": actual_return,
                        "direction_hit_window": int(pred_return * actual_return > 0),
                        "pred_path_consistency": 1.0 if pred_return > 0 else 0.4,
                        "pred_range_pct": 0.05,
                        "history_mean_amount": 1000 + symbol_idx * 100,
                        "history_volatility_pct": 0.05,
                        "mode": "kronos",
                    }
                )
            window_id += 1
    csv_path = tmp_path / "rolling_pred.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    result = rolling_validate_filters(
        csv_path,
        top_k=2,
        min_trades=1,
        min_periods=1,
        min_coverage=0.1,
        train_periods=4,
        test_periods=2,
        step_periods=2,
    )
    result = write_rolling_filter_report(result, tmp_path, "rolling_unit")

    assert result["summary"]["fold_count"] == 2
    assert "overfit_gap_pct" in result["summary"]
    assert result["folds"][0]["test_trade_count"] >= 1
    assert "rolling_filter_validation.json" in result["artifact_paths"]["json"]
