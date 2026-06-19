import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


def _write_sb3_fixture(tmp_path: Path, *, rows: int = 32) -> Path:
    csv_dir = tmp_path / "qlib_csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    base = pd.Timestamp("2025-01-03 09:00:00")
    csv_paths = []
    for symbol, session in [
        ("KR000001", "20250103"),
        ("KR000002", "20250106"),
        ("KR000003", "20250107"),
    ]:
        csv_path = csv_dir / f"{symbol}_{session}.csv"
        frame = pd.DataFrame(
            {
                "symbol": symbol,
                "date": [(base + pd.Timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(rows)],
                "open": [100.0 + i * 0.1 for i in range(rows)],
                "high": [100.1 + i * 0.1 for i in range(rows)],
                "low": [99.9 + i * 0.1 for i in range(rows)],
                "close": [100.0 + i * 0.1 for i in range(rows)],
                "volume": [10.0 + i for i in range(rows)],
                "amount": [(100.0 + i * 0.1) * (10.0 + i) for i in range(rows)],
            }
        )
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        csv_paths.append((csv_path, symbol, session))

    episodes = []
    for idx, (csv_path, symbol, session) in enumerate(csv_paths):
        episodes.append(
            {
                "episode_id": f"{symbol}_{session}",
                "symbol": symbol,
                "instrument": symbol,
                "session": session,
                "split": "train" if idx == 0 else "test",
                "time_start": "090000",
                "time_end": "090031",
                "lookback_window": 5,
                "reward_horizon_seconds": 3,
                "row_count": rows,
                "source_csv": str(csv_path),
            }
        )
    manifest_path = tmp_path / "episode_manifest.json"
    manifest_path.write_text(
        json.dumps({"mode": "stom_rl_episode_manifest", "summary": {"episode_count": 3}, "episodes": episodes}),
        encoding="utf-8-sig",
    )
    return manifest_path


_SKIP_MARKERS = (
    "ModuleNotFoundError",
    "DLL load failed",
    "WinError 1114",
    "c10.dll",
    "Error loading",
)


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        check=False,
    )
    combined = result.stderr + result.stdout
    if result.returncode != 0 and any(marker in combined for marker in _SKIP_MARKERS):
        pytest.skip(combined)
    return result


def test_sb3_eval_reuses_saved_model_without_retraining(tmp_path):
    manifest_path = _write_sb3_fixture(tmp_path)
    train_dir = tmp_path / "sb3_train"
    eval_dir = tmp_path / "sb3_eval"

    result = _run_python(
        f"""
import json
from stom_rl.sb3_smoke import Sb3SmokeConfig, run_sb3_smoke
from stom_rl.sb3_eval import Sb3EvalConfig, run_sb3_eval

run_sb3_smoke(
    Sb3SmokeConfig(
        manifest_path={str(manifest_path)!r},
        output_dir={str(train_dir)!r},
        algorithms=("dqn",),
        total_timesteps=64,
        max_eval_episodes=1,
        max_eval_steps_per_episode=6,
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
    )
)

payload = run_sb3_eval(
    Sb3EvalConfig(
        model_dir={str(train_dir)!r},
        algorithms=("dqn",),
        eval_episodes=2,
        max_eval_steps_per_episode=6,
        manifest_path={str(manifest_path)!r},
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
        output_dir={str(eval_dir)!r},
    )
)
row = payload["models"][0]
print(json.dumps({{
    "mode": payload["mode"],
    "eval_only_summary": payload["summary"]["eval_only"],
    "model": row["model"],
    "eval_only": row["eval_only"],
    "episode_count": row["episode_count"],
    "training_elapsed_seconds": row["training_elapsed_seconds"],
    "source_model": row["source_model"],
    "training_timesteps": row["training_timesteps"],
}}))
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["mode"] == "stom_rl_sb3_eval"
    assert payload["eval_only_summary"] is True
    assert payload["eval_only"] is True
    assert payload["model"].endswith("_eval")
    assert payload["episode_count"] == 2
    assert payload["training_elapsed_seconds"] == 0.0
    assert payload["training_timesteps"] == 64
    assert payload["source_model"] == "dqn_smoke"

    assert (eval_dir / "sb3_smoke_summary.json").is_file()
    assert (eval_dir / "sb3_smoke_summary.csv").is_file()
    assert (eval_dir / "actions.csv").is_file()
    assert (eval_dir / "trades.csv").is_file()
    assert (eval_dir / "equity.csv").is_file()
    assert (eval_dir / "episodes.csv").is_file()
    assert (eval_dir / "rl_live_events.jsonl").is_file()
    assert (eval_dir / "rl_live_summary.json").is_file()


def test_sb3_eval_run_is_distinct_leaderboard_row(tmp_path):
    manifest_path = _write_sb3_fixture(tmp_path)
    rl_root = tmp_path / "webui" / "rl_runs"
    train_dir = rl_root / "stom_1s_2025_sb3_50k"
    eval_dir = rl_root / "stom_1s_2025_sb3_50k_eval2"

    result = _run_python(
        f"""
import json
from stom_rl.sb3_smoke import Sb3SmokeConfig, run_sb3_smoke
from stom_rl.sb3_eval import Sb3EvalConfig, run_sb3_eval

# Train a tiny model but stamp a large source training_timesteps so the
# leaderboard derives a distinct 'dqn_50k' style name.
run_sb3_smoke(
    Sb3SmokeConfig(
        manifest_path={str(manifest_path)!r},
        output_dir={str(train_dir)!r},
        algorithms=("dqn",),
        total_timesteps=64,
        max_eval_episodes=1,
        max_eval_steps_per_episode=6,
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
    )
)

# Rewrite the source summary's training_timesteps to 50000 to emulate a real
# 50k training run that produced the saved model.
summary_path = {str(train_dir / "sb3_smoke_summary.json")!r}
summary = json.loads(open(summary_path, encoding="utf-8-sig").read())
for model_row in summary["models"]:
    model_row["training_timesteps"] = 50000
open(summary_path, "w", encoding="utf-8-sig").write(json.dumps(summary, ensure_ascii=False))

run_sb3_eval(
    Sb3EvalConfig(
        model_dir={str(train_dir)!r},
        algorithms=("dqn",),
        eval_episodes=2,
        max_eval_steps_per_episode=6,
        manifest_path={str(manifest_path)!r},
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
        output_dir={str(eval_dir)!r},
    )
)
print("OK")
"""
    )

    assert result.returncode == 0, result.stderr

    # Build a leaderboard discovering the rl_root; both the training run and the
    # eval run live under it and should appear as distinct rows.
    from stom_rl.performance_leaderboard import (
        PerformanceLeaderboardConfig,
        build_performance_leaderboard,
    )

    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    baseline_report = baseline_dir / "leaderboard_report.json"
    baseline_report.write_text(
        json.dumps(
            {
                "summary": {
                    "target_rows": [
                        {"policy": "buy_and_hold", "avg_episode_net_return_pct": 0.5, "episode_count": 1},
                        {"policy": "no_trade", "avg_episode_net_return_pct": 0.0, "episode_count": 1},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    bandit_dir = tmp_path / "bandit"
    bandit_dir.mkdir()
    bandit_report = bandit_dir / "eval_summary.json"
    bandit_report.write_text(
        json.dumps({"eval_summary": {"summary": {"policy": "contextual_bandit", "avg_episode_net_return_pct": 0.1}}}),
        encoding="utf-8",
    )

    payload = build_performance_leaderboard(
        PerformanceLeaderboardConfig(
            baseline_report=str(baseline_report),
            contextual_bandit_report=str(bandit_report),
            sb3_smoke_reports=("auto",),
            sb3_report_root=str(rl_root),
            output_dir=str(tmp_path / "out"),
        )
    )

    rows = {row["model"]: row for row in payload["leaderboard"]}
    eval_rows = [row for row in payload["leaderboard"] if row.get("eval_only")]
    assert len(eval_rows) == 1
    eval_row = eval_rows[0]
    assert eval_row["model"].endswith("_eval")
    assert eval_row["is_smoke"] is False
    assert "dqn_50k" in rows
    assert "dqn_50k_eval" in rows
    # Training row and eval row are distinct, non-colliding leaderboard entries.
    assert eval_row["model"] != "dqn_50k"
    assert payload["summary"]["rl_eval_only_models"] == ["dqn_50k_eval"]
