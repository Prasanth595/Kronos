import json

import pytest

from stom_rl.opening_30m_rl_train import (
    OpeningTrainingConfig,
    OpeningTrainingError,
    run_opening_training_stage,
)
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames


def test_opening_training_stage_runs_tiny_dqn_fixed_entry_exit(tmp_path):
    frames = build_opening_fixture_frames()

    payload = run_opening_training_stage(
        frames,
        train_episode_ids=("000250_20250103", "005930_20250106"),
        eval_episode_ids=("000660_20250107",),
        config=OpeningTrainingConfig(output_dir=tmp_path / "train", total_timesteps=8, seed=123),
    )

    assert payload["artifact_type"] == "opening_30m_training_stage"
    assert payload["status"] in {"passed", "skipped_sb3_unavailable"}
    assert payload["algorithm"] == "DQN"
    assert payload["fixed_entry_exit_only"] is True
    assert payload["seed"] == 123
    assert payload["train_episode_count"] == 2
    assert payload["eval_episode_count"] == 1
    assert set(payload["train_episode_ids"]).isdisjoint(payload["eval_episode_ids"])
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert "not live-ready" in payload["safety_note"]
    saved = json.loads((tmp_path / "train" / "opening_training_summary.json").read_text(encoding="utf-8"))
    if payload["status"] == "passed":
        assert (tmp_path / "train" / "dqn_model.zip").is_file()
        assert saved["model_files"]["dqn"].endswith("dqn_model.zip")
    else:
        assert payload["sb3_status"] == "skipped_sb3_unavailable"
        assert saved["model_files"] == {}


def test_opening_training_rejects_overlapping_train_eval_episode_ids(tmp_path):
    with pytest.raises(OpeningTrainingError, match="overlap"):
        run_opening_training_stage(
            build_opening_fixture_frames(),
            train_episode_ids=("000250_20250103",),
            eval_episode_ids=("000250_20250103",),
            config=OpeningTrainingConfig(output_dir=tmp_path / "overlap", total_timesteps=1),
        )

    assert not (tmp_path / "overlap").exists()
