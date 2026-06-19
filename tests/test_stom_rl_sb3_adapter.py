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
    for symbol, session in [("KR000001", "20250103"), ("KR000002", "20250106")]:
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
        json.dumps({"mode": "stom_rl_episode_manifest", "summary": {"episode_count": 2}, "episodes": episodes}),
        encoding="utf-8-sig",
    )
    return manifest_path


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 and "ModuleNotFoundError" in (result.stderr + result.stdout):
        pytest.skip(result.stderr or result.stdout)
    return result


def test_stom_gymnasium_adapter_passes_sb3_check_env(tmp_path):
    manifest_path = _write_sb3_fixture(tmp_path)

    result = _run_python(
        f"""
import json
from stable_baselines3.common.env_checker import check_env
from stom_rl.sb3_adapter import make_sb3_env

env = make_sb3_env(
    {str(manifest_path)!r},
    split="train",
    episode_index=0,
    lookback_window=5,
    reward_horizon_seconds=3,
    cost_bps=0.0,
)
check_env(env, warn=True, skip_render_check=True)
observation, info = env.reset(seed=7)
print(json.dumps({{"shape": list(observation.shape), "contains": env.observation_space.contains(observation), "no_future": info["no_future_observation"]}}))
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"shape": [5, 9], "contains": True, "no_future": True}


def test_sb3_smoke_runner_writes_dqn_and_ppo_summary(tmp_path):
    manifest_path = _write_sb3_fixture(tmp_path)
    output_dir = tmp_path / "sb3_out"

    result = _run_python(
        f"""
import json
from stom_rl.sb3_smoke import Sb3SmokeConfig, run_sb3_smoke

payload = run_sb3_smoke(
    Sb3SmokeConfig(
        manifest_path={str(manifest_path)!r},
        output_dir={str(output_dir)!r},
        algorithms=("dqn", "ppo"),
        total_timesteps=8,
        max_eval_episodes=1,
        max_eval_steps_per_episode=6,
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
    )
)
print(json.dumps({{"passed": payload["check_env"]["passed"], "algorithms": [row["algorithm"] for row in payload["models"]]}}))
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["passed"] is True
    assert set(payload["algorithms"]) == {"dqn", "ppo"}
    assert (tmp_path / "sb3_out" / "sb3_smoke_summary.json").is_file()
    assert (tmp_path / "sb3_out" / "rl_live_events.jsonl").is_file()
    assert (tmp_path / "sb3_out" / "rl_live_summary.json").is_file()
    summary = json.loads((tmp_path / "sb3_out" / "sb3_smoke_summary.json").read_text(encoding="utf-8-sig"))
    assert summary["summary"]["live_event_count"] > 0
    assert "eval" in summary["summary"]["live_event_phases"]
    assert (tmp_path / "sb3_out" / "dqn_model.zip").is_file()
    assert (tmp_path / "sb3_out" / "ppo_model.zip").is_file()
