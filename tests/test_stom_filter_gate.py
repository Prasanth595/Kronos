import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "finetune"))
sys.path.insert(0, str(REPO_ROOT / "webui"))

from search_stom_1s_filters import FilterSpec, _selected_rows, build_cost_gate_report, write_cost_gate_report  # noqa: E402
import stom_dashboard  # noqa: E402
import pandas as pd


def _latest_row(window_id, asof_timestamp, pred_return):
    return {
        "window_id": window_id,
        "asof_timestamp": asof_timestamp,
        "pred_return_window": pred_return,
        "pred_path_consistency": 1.0,
        "history_mean_amount": 10,
        "pred_range_pct": 0.1,
        "history_volatility_pct": 0.1,
    }


def test_selected_rows_keeps_top_k_per_asof_after_vectorized_filtering():
    latest = pd.DataFrame(
        [
            _latest_row(1, "2026-01-02 09:05:00", 0.2),
            _latest_row(2, "2026-01-02 09:05:00", 0.5),
            _latest_row(3, "2026-01-02 09:10:00", 0.1),
            _latest_row(4, "2026-01-02 09:10:00", 0.4),
        ]
    )
    latest["asof_timestamp"] = pd.to_datetime(latest["asof_timestamp"])

    selected = _selected_rows(latest, FilterSpec(0.0, 0.0, None, 0.0, None), top_k=1)

    assert selected["window_id"].tolist() == [2, 4]


def test_cost_gate_report_blocks_target_cost_but_keeps_low_cost_scenario_visible(tmp_path, monkeypatch):
    filter_report = tmp_path / "sample.filter_search.json"
    filter_report.write_text(
        json.dumps(
            {
                "cost_bps": 15,
                "slippage_bps": 10,
                "baseline_topk": {
                    "filter_name": "baseline",
                    "avg_gross_return_pct": 0.05,
                    "avg_net_return_pct": -0.20,
                    "period_count": 4,
                    "trade_count": 20,
                    "coverage": 1.0,
                    "direction_hit_rate": 0.45,
                },
                "top_filters": [
                    {
                        "filter_name": "ret>=0.05|cons>=0.8",
                        "avg_gross_return_pct": 0.12,
                        "avg_net_return_pct": -0.13,
                        "period_count": 4,
                        "trade_count": 12,
                        "coverage": 1.0,
                        "direction_hit_rate": 0.55,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rolling_report = tmp_path / "sample.rolling_filter_validation.json"
    rolling_report.write_text(
        json.dumps(
            {
                "cost_bps": 15,
                "slippage_bps": 10,
                "summary": {"avg_test_net_return_pct": -0.175},
                "folds": [
                    {
                        "fold": 1,
                        "selected_filter": "a",
                        "train_avg_net_return_pct": 0.05,
                        "test_avg_gross_return_pct": 0.30,
                        "test_avg_net_return_pct": 0.05,
                        "baseline_test_avg_net_return_pct": -0.10,
                        "test_trade_count": 60,
                        "test_direction_hit_rate": 0.6,
                    },
                    {
                        "fold": 2,
                        "selected_filter": "b",
                        "train_avg_net_return_pct": 0.00,
                        "test_avg_gross_return_pct": 0.10,
                        "test_avg_net_return_pct": -0.15,
                        "baseline_test_avg_net_return_pct": -0.20,
                        "test_trade_count": 60,
                        "test_direction_hit_rate": 0.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_cost_gate_report(
        filter_report,
        rolling_report,
        total_cost_bps_grid=[5, 25],
        target_total_cost_bps=25,
        min_total_test_trades=100,
    )

    assert result["decision"] == "hold_expand_200k"
    by_cost = {row["total_cost_bps"]: row for row in result["rolling_cost_sensitivity"]}
    assert by_cost[5.0]["passes_gate"] is True
    assert by_cost[25.0]["passes_gate"] is False
    assert by_cost[25.0]["avg_test_net_return_pct"] < 0
    assert result["filter_cost_sensitivity"][0]["filter_name"] == "ret>=0.05|cons>=0.8"

    written = write_cost_gate_report(result, tmp_path, "sample")
    monkeypatch.setattr(stom_dashboard, "FILTER_REPORT_DIRS", [tmp_path])
    files = stom_dashboard.list_filter_report_files()
    loaded = stom_dashboard.load_filter_report_artifact(Path(written["artifact_paths"]["json"]).name)

    assert any(file["artifact_type"] == "cost_sensitivity_gate" for file in files)
    assert loaded["artifact_type"] == "cost_sensitivity_gate"
