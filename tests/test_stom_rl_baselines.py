import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from stom_rl.baselines import BaselineRunConfig, _parse_policies, run_baselines


def _write_baseline_fixture(tmp_path: Path, *, rows: int = 24) -> Path:
    csv_dir = tmp_path / "qlib_csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / "KR000001_20250103.csv"
    base = pd.Timestamp("2025-01-03 09:00:00")
    frame = pd.DataFrame(
        {
            "symbol": "KR000001",
            "date": [(base + pd.Timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(rows)],
            "open": [100.0 + i for i in range(rows)],
            "high": [100.0 + i for i in range(rows)],
            "low": [100.0 + i for i in range(rows)],
            "close": [100.0 + i for i in range(rows)],
            "volume": [10.0 + i for i in range(rows)],
            "amount": [(100.0 + i) * (10.0 + i) for i in range(rows)],
            "money": [(100.0 + i) * (10.0 + i) for i in range(rows)],
            "factor": 1.0,
        }
    )
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    manifest = {
        "mode": "stom_rl_episode_manifest",
        "summary": {"episode_count": 1},
        "episodes": [
            {
                "episode_id": "000001_20250103",
                "symbol": "000001",
                "instrument": "KR000001",
                "session": "20250103",
                "split": "test",
                "time_start": "090000",
                "time_end": "093000",
                "lookback_window": 5,
                "reward_horizon_seconds": 3,
                "row_count": rows,
                "source_csv": str(csv_path),
            }
        ],
    }
    manifest_path = tmp_path / "episode_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8-sig")
    return manifest_path


def _summary_by_policy(payload):
    return {item["policy"]: item for item in payload["summary"]["policies"]}


def test_baseline_runner_writes_summary_and_policy_artifacts(tmp_path):
    manifest_path = _write_baseline_fixture(tmp_path)
    output_dir = tmp_path / "baseline_run"

    payload = run_baselines(
        BaselineRunConfig(
            manifest_path=str(manifest_path),
            output_dir=str(output_dir),
            split="test",
            policies=("no_trade", "buy_and_hold", "momentum"),
            max_episodes=1,
            lookback_window=5,
            reward_horizon_seconds=3,
            cost_bps=0.0,
            write_artifacts=True,
        )
    )

    summaries = _summary_by_policy(payload)
    assert payload["summary"]["policy_count"] == 3
    assert summaries["no_trade"]["trade_count"] == 0
    assert summaries["no_trade"]["avg_episode_net_return_pct"] == pytest.approx(0.0)
    assert summaries["buy_and_hold"]["trade_count"] == 1
    assert summaries["buy_and_hold"]["avg_episode_net_return_pct"] > 0
    assert summaries["momentum"]["trade_count"] >= 1

    assert (output_dir / "baseline_summary.json").is_file()
    assert (output_dir / "baseline_summary.csv").is_file()
    assert (output_dir / "buy_and_hold" / "trades.csv").is_file()
    assert (output_dir / "buy_and_hold" / "equity.csv").is_file()
    with (output_dir / "buy_and_hold" / "trades.csv").open(encoding="utf-8-sig", newline="") as f:
        trade_rows = list(csv.DictReader(f))
    assert trade_rows[0]["forced_exit"] == "True"


def test_random_baseline_is_deterministic_for_same_seed(tmp_path):
    manifest_path = _write_baseline_fixture(tmp_path)
    config = BaselineRunConfig(
        manifest_path=str(manifest_path),
        output_dir=str(tmp_path / "ignored"),
        split="test",
        policies=("random",),
        max_episodes=1,
        seed=77,
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        write_artifacts=False,
    )

    first = run_baselines(config)
    second = run_baselines(config)

    assert first["summary"]["policies"] == second["summary"]["policies"]
    assert first["summary"]["ranking"] == second["summary"]["ranking"]


def test_parse_policies_rejects_unknown_policy():
    with pytest.raises(ValueError, match="Unknown policies"):
        _parse_policies("no_trade,unknown_policy")
