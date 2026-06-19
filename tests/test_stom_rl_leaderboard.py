import json
from pathlib import Path

import pandas as pd

from stom_rl.leaderboard import LeaderboardConfig, run_leaderboard


def _write_manifest(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    rows = []
    for episode_idx, trend in enumerate([1.0, -1.0], start=1):
        frame = pd.DataFrame(
            {
                "symbol": [f"KRTEST{episode_idx}"] * 16,
                "date": pd.date_range("2026-01-02 09:00:00", periods=16, freq="s"),
                "open": [100 + trend * i for i in range(16)],
                "high": [100 + trend * i for i in range(16)],
                "low": [100 + trend * i for i in range(16)],
                "close": [100 + trend * i for i in range(16)],
                "volume": [1000 + i for i in range(16)],
                "amount": [1000 + i * 10 for i in range(16)],
            }
        )
        source = csv_dir / f"KRTEST{episode_idx}_20260102.csv"
        frame.to_csv(source, index=False)
        rows.append(
            {
                "episode_id": f"KRTEST{episode_idx}_20260102",
                "symbol": f"TEST{episode_idx}",
                "session": "20260102",
                "split": "test",
                "source_csv": str(source),
            }
        )
    manifest = {
        "mode": "stom_rl_episode_manifest",
        "episodes": rows,
    }
    manifest_path = tmp_path / "episode_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def test_compact_leaderboard_writes_summary_artifacts(tmp_path):
    manifest = _write_manifest(tmp_path)
    output_dir = tmp_path / "leaderboard"

    payload = run_leaderboard(
        LeaderboardConfig(
            manifest_path=str(manifest),
            output_dir=str(output_dir),
            split="test",
            policies=("no_trade", "buy_and_hold", "momentum"),
            cost_bps_values=(0.0, 25.0),
            target_cost_bps=25.0,
            lookback_window=3,
            reward_horizon_seconds=3,
            momentum_window=2,
            volume_window=2,
        )
    )

    assert payload["summary"]["episode_count"] == 2
    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["best_policy_at_target_cost"] in {"no_trade", "buy_and_hold", "momentum"}
    assert (output_dir / "leaderboard_report.json").is_file()
    assert (output_dir / "leaderboard.csv").is_file()
    assert (output_dir / "target_policy_episodes.csv").is_file()
