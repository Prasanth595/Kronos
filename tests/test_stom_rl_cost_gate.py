import csv
import json
from pathlib import Path

import pandas as pd

from stom_rl.cost_gate import CostGateConfig, run_cost_gate


def _write_cost_gate_fixture(tmp_path: Path, *, rows: int = 24) -> Path:
    csv_dir = tmp_path / "qlib_csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    episodes = []
    for day_offset, session in enumerate(["20250103", "20250106"]):
        csv_path = csv_dir / f"KR000001_{session}.csv"
        base = pd.Timestamp(f"{session[:4]}-{session[4:6]}-{session[6:]} 09:00:00")
        price_base = 100.0 + day_offset
        frame = pd.DataFrame(
            {
                "symbol": "KR000001",
                "date": [(base + pd.Timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(rows)],
                "open": [price_base + i for i in range(rows)],
                "high": [price_base + i for i in range(rows)],
                "low": [price_base + i for i in range(rows)],
                "close": [price_base + i for i in range(rows)],
                "volume": [10.0 + i for i in range(rows)],
                "amount": [(price_base + i) * (10.0 + i) for i in range(rows)],
                "money": [(price_base + i) * (10.0 + i) for i in range(rows)],
                "factor": 1.0,
            }
        )
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        episodes.append(
            {
                "episode_id": f"000001_{session}",
                "symbol": "000001",
                "instrument": "KR000001",
                "session": session,
                "split": "test",
                "time_start": "090000",
                "time_end": "093000",
                "lookback_window": 5,
                "reward_horizon_seconds": 3,
                "row_count": rows,
                "source_csv": str(csv_path),
            }
        )

    manifest = {
        "mode": "stom_rl_episode_manifest",
        "summary": {"episode_count": len(episodes)},
        "episodes": episodes,
    }
    manifest_path = tmp_path / "episode_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8-sig")
    return manifest_path


def test_cost_gate_writes_scenario_rolling_and_gate_artifacts(tmp_path):
    manifest_path = _write_cost_gate_fixture(tmp_path)
    output_dir = tmp_path / "cost_gate"

    payload = run_cost_gate(
        CostGateConfig(
            manifest_path=str(manifest_path),
            output_dir=str(output_dir),
            split="test",
            policies=("no_trade", "buy_and_hold", "momentum"),
            cost_bps_values=(0.0, 25.0),
            slippage_bps_values=(0.0,),
            target_cost_bps=25.0,
            max_episodes=2,
            lookback_window=5,
            reward_horizon_seconds=3,
            max_drawdown_pct=50.0,
            max_trades_per_episode=10.0,
            rolling_sessions_per_fold=1,
            rolling_max_folds=2,
            rolling_max_episodes_per_fold=1,
            write_policy_artifacts=False,
        )
    )

    assert payload["summary"]["scenario_count"] == 2
    assert payload["summary"]["policy_count"] == 3
    assert payload["summary"]["passing_policy_count"] >= 1
    assert "buy_and_hold" in payload["summary"]["passing_policies"]
    assert len(payload["scenario_rows"]) == 6
    assert len(payload["rolling_rows"]) == 6

    report_path = output_dir / "cost_gate_report.json"
    scenario_csv = output_dir / "scenario_summary.csv"
    rolling_csv = output_dir / "rolling_folds.csv"
    gate_csv = output_dir / "gate_summary.csv"
    assert report_path.is_file()
    assert scenario_csv.is_file()
    assert rolling_csv.is_file()
    assert gate_csv.is_file()

    with gate_csv.open(encoding="utf-8-sig", newline="") as f:
        gate_rows = {row["policy"]: row for row in csv.DictReader(f)}
    assert gate_rows["no_trade"]["passes_cost_gate"] == "False"
    assert gate_rows["buy_and_hold"]["passes_cost_gate"] == "True"


def test_cost_gate_can_limit_to_specific_sessions(tmp_path):
    manifest_path = _write_cost_gate_fixture(tmp_path)
    output_dir = tmp_path / "cost_gate_session_filter"

    payload = run_cost_gate(
        CostGateConfig(
            manifest_path=str(manifest_path),
            output_dir=str(output_dir),
            split="test",
            policies=("buy_and_hold",),
            cost_bps_values=(0.0,),
            slippage_bps_values=(0.0,),
            target_cost_bps=0.0,
            sessions=("20250106",),
            max_episodes=0,
            lookback_window=5,
            reward_horizon_seconds=3,
            rolling_sessions_per_fold=1,
            rolling_max_folds=0,
            rolling_max_episodes_per_fold=0,
        )
    )

    assert payload["scenario_rows"][0]["episode_count"] == 1
    assert len(payload["rolling_rows"]) == 1
    assert payload["rolling_rows"][0]["sessions"] == "20250106"
