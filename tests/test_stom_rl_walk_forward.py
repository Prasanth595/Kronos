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
    # One train session plus four contiguous test sessions so a 2-fold split has
    # two distinct, non-overlapping time periods.
    for symbol, session, split in [
        ("KR000001", "20250103", "train"),
        ("KR000002", "20250106", "test"),
        ("KR000003", "20250107", "test"),
        ("KR000004", "20250108", "test"),
        ("KR000005", "20250109", "test"),
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
        csv_paths.append((csv_path, symbol, session, split))

    episodes = []
    for csv_path, symbol, session, split in csv_paths:
        episodes.append(
            {
                "episode_id": f"{symbol}_{session}",
                "symbol": symbol,
                "instrument": symbol,
                "session": session,
                "split": split,
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
        json.dumps(
            {"mode": "stom_rl_episode_manifest", "summary": {"episode_count": len(episodes)}, "episodes": episodes}
        ),
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


def test_session_binning_is_contiguous_and_complete():
    """Unit test: session folds are contiguous, non-overlapping, and cover all sessions."""

    from stom_rl.walk_forward import _build_session_folds

    # 6 episodes across 6 distinct, time-ordered sessions.
    sessions = ["20250101", "20250102", "20250103", "20250104", "20250105", "20250106"]
    episodes = [{"episode_id": f"e{i}", "session": session} for i, session in enumerate(sessions)]

    folds = _build_session_folds(episodes, n_folds=3, max_episodes_per_fold=30)
    assert len(folds) == 3

    # Indices partition [0..5] with no overlap, covering everything.
    all_indices = [idx for fold in folds for idx in fold["episode_indices"]]
    assert sorted(all_indices) == list(range(len(sessions)))
    assert len(all_indices) == len(set(all_indices))

    # Each fold is contiguous in time, and folds do not overlap in session ranges.
    prev_end = None
    for fold in folds:
        fold_indices = fold["episode_indices"]
        assert fold_indices == sorted(fold_indices)
        assert fold["period_start"] <= fold["period_end"]
        if prev_end is not None:
            assert fold["period_start"] > prev_end
        prev_end = fold["period_end"]

    # A single session must never span two folds.
    seen_sessions = set()
    for fold in folds:
        fold_sessions = {sessions[idx] for idx in fold["episode_indices"]}
        assert not (fold_sessions & seen_sessions)
        seen_sessions |= fold_sessions
    assert seen_sessions == set(sessions)


def test_walk_forward_evaluates_saved_model_across_folds(tmp_path):
    manifest_path = _write_sb3_fixture(tmp_path)
    train_dir = tmp_path / "sb3_train"
    wf_dir = tmp_path / "walk_forward"

    result = _run_python(
        f"""
import json
from stom_rl.sb3_smoke import Sb3SmokeConfig, run_sb3_smoke
from stom_rl.walk_forward import WalkForwardConfig, run_walk_forward

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

payload = run_walk_forward(
    WalkForwardConfig(
        model_dir={str(train_dir)!r},
        algorithms=("dqn",),
        n_folds=2,
        max_episodes_per_fold=2,
        max_eval_steps_per_episode=6,
        manifest_path={str(manifest_path)!r},
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        device="cpu",
        output_dir={str(wf_dir)!r},
    )
)
dqn_folds = [row for row in payload["folds"] if row["algorithm"] == "dqn"]
algo_summary = payload["summary"]["per_algorithm"][0]
print(json.dumps({{
    "mode": payload["mode"],
    "n_folds": payload["summary"]["n_folds"],
    "fold_count": len(dqn_folds),
    "fold_indices": [row["fold_index"] for row in dqn_folds],
    "period_starts": [row["period_start"] for row in dqn_folds],
    "period_ends": [row["period_end"] for row in dqn_folds],
    "episode_counts": [row["episode_count"] for row in dqn_folds],
    "have_avg_net": all("avg_episode_net_return_pct" in row for row in dqn_folds),
    "have_max_dd": all("max_drawdown_pct" in row for row in dqn_folds),
    "folds_positive": algo_summary["folds_positive"],
    "consistency": algo_summary["consistency"],
    "mean_fold_avg_net": algo_summary["mean_fold_avg_net"],
    "source_model": dqn_folds[0]["source_model"],
}}))
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["mode"] == "stom_rl_walk_forward"
    assert payload["n_folds"] == 2
    assert payload["fold_count"] == 2

    # Two distinct folds with distinct, ordered time periods.
    assert payload["fold_indices"] == [0, 1]
    assert payload["period_starts"][0] != payload["period_starts"][1]
    assert payload["period_ends"][0] != payload["period_ends"][1]
    assert payload["period_starts"][0] <= payload["period_ends"][0]
    assert payload["period_ends"][0] < payload["period_starts"][1]

    assert all(count >= 1 for count in payload["episode_counts"])
    assert payload["have_avg_net"] is True
    assert payload["have_max_dd"] is True

    # Per-algorithm aggregate fields present.
    assert "folds_positive" in payload
    assert payload["consistency"] in {"consistent", "regime_sensitive", "unstable"}
    assert isinstance(payload["mean_fold_avg_net"], (int, float))
    assert payload["source_model"] == "dqn_smoke"

    # Artifacts written.
    assert (wf_dir / "walk_forward_report.json").is_file()
    assert (wf_dir / "walk_forward_folds.csv").is_file()
