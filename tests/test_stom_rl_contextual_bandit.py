import json
from pathlib import Path

import pandas as pd

from stom_rl.contextual_bandit import (
    ContextualBanditConfig,
    _raw_features,
    load_model,
    run_contextual_bandit,
)


def _write_bandit_fixture(tmp_path: Path, *, rows: int = 28) -> Path:
    csv_dir = tmp_path / "qlib_csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    episodes = []
    specs = [
        ("train", "20250103", 100.0, 1.0),
        ("train", "20250106", 101.0, 1.0),
        ("test", "20250107", 102.0, 1.0),
    ]
    for split, session, price_base, slope in specs:
        csv_path = csv_dir / f"KR000001_{session}.csv"
        base = pd.Timestamp(f"{session[:4]}-{session[4:6]}-{session[6:]} 09:00:00")
        close = [price_base + slope * i for i in range(rows)]
        frame = pd.DataFrame(
            {
                "symbol": "KR000001",
                "date": [(base + pd.Timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(rows)],
                "open": close,
                "high": [value + 0.1 for value in close],
                "low": [value - 0.1 for value in close],
                "close": close,
                "volume": [10.0 + i for i in range(rows)],
                "amount": [close[i] * (10.0 + i) for i in range(rows)],
                "money": [close[i] * (10.0 + i) for i in range(rows)],
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
                "split": split,
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


def test_contextual_bandit_trains_saves_loads_and_evaluates(tmp_path):
    manifest_path = _write_bandit_fixture(tmp_path)
    output_dir = tmp_path / "bandit_run"

    payload = run_contextual_bandit(
        ContextualBanditConfig(
            manifest_path=str(manifest_path),
            output_dir=str(output_dir),
            train_split="train",
            eval_split="test",
            max_train_episodes=2,
            max_eval_episodes=1,
            train_sample_stride=1,
            eval_sample_stride=1,
            lookback_window=5,
            reward_horizon_seconds=3,
            cost_bps=0.0,
            ridge_alpha=0.1,
            write_artifacts=True,
        )
    )

    summary = payload["eval_summary"]
    assert summary["policy"] == "contextual_bandit"
    assert summary["episode_count"] == 1
    assert summary["trade_count"] >= 1
    assert summary["avg_episode_net_return_pct"] > 0
    assert summary["passes_cost_gate"] is True

    assert (output_dir / "model.json").is_file()
    assert (output_dir / "eval_summary.json").is_file()
    assert (output_dir / "actions.csv").is_file()
    assert (output_dir / "trades.csv").is_file()
    model = load_model(output_dir / "model.json")

    test_csv = Path(json.loads(manifest_path.read_text(encoding="utf-8-sig"))["episodes"][2]["source_csv"])
    frame = pd.read_csv(test_csv)
    score = model.predict_score(_raw_features(frame, 5, 5))
    assert score > 0


def test_contextual_bandit_can_run_without_writing_artifacts(tmp_path):
    manifest_path = _write_bandit_fixture(tmp_path)
    output_dir = tmp_path / "no_write_run"

    payload = run_contextual_bandit(
        ContextualBanditConfig(
            manifest_path=str(manifest_path),
            output_dir=str(output_dir),
            train_split="train",
            eval_split="test",
            max_train_episodes=1,
            max_eval_episodes=1,
            train_sample_stride=2,
            eval_sample_stride=2,
            lookback_window=5,
            reward_horizon_seconds=3,
            cost_bps=0.0,
            write_artifacts=False,
        )
    )

    assert payload["model"]["train_summary"]["train_sample_count"] > 0
    assert output_dir.exists() is False
