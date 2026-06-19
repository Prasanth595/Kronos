import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stom_rl.trading_env import (
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_SELL,
    StomTickTradingEnv,
    StomTickTradingEnvConfig,
)


def _write_env_fixture(tmp_path: Path, *, rows: int = 16) -> Path:
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
                "split": "train",
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


def _env(tmp_path: Path, **overrides):
    manifest_path = _write_env_fixture(tmp_path)
    config = StomTickTradingEnvConfig(
        manifest_path=str(manifest_path),
        split="train",
        episode_id="000001_20250103",
        lookback_window=5,
        reward_horizon_seconds=3,
        cost_bps=0.0,
        slippage_bps=0.0,
        invalid_action_penalty=0.01,
        **overrides,
    )
    return StomTickTradingEnv(config)


def test_reset_returns_gymnasium_style_observation_without_future_leakage(tmp_path):
    env = _env(tmp_path)

    observation, info = env.reset(seed=7)

    assert observation.shape == (5, 9)
    assert env.observation_space.contains(observation)
    assert info["event"] == "reset"
    assert info["last_observation_timestamp"] == "2025-01-03T09:00:04"
    assert info["action_timestamp"] == "2025-01-03T09:00:05"
    assert info["horizon_timestamp"] == "2025-01-03T09:00:08"
    assert info["no_future_observation"] is True
    assert info["feature_columns"] == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "position",
        "unrealized_return",
        "time_in_position",
    ]


def test_horizon_reward_buy_hold_sell_and_invalid_actions(tmp_path):
    env = _env(tmp_path)
    env.reset(seed=7)

    _, buy_reward, terminated, truncated, buy_info = env.step(ACTION_BUY)
    expected_horizon_return = (108.0 - 105.0) / 105.0
    assert buy_reward == pytest.approx(expected_horizon_return)
    assert buy_info["position_after"] == 1
    assert buy_info["invalid_action"] is False
    assert terminated is False
    assert truncated is False

    _, invalid_reward, _, _, invalid_info = env.step(ACTION_BUY)
    assert invalid_reward < 0
    assert invalid_info["invalid_action"] is True
    assert invalid_info["invalid_action_count"] == 1

    _, sell_reward, _, _, sell_info = env.step(ACTION_SELL)
    expected_realized = (107.0 - 105.0) / 105.0
    assert sell_reward == pytest.approx(expected_realized)
    assert sell_info["position_after"] == 0

    _, invalid_sell_reward, _, _, invalid_sell_info = env.step(ACTION_SELL)
    assert invalid_sell_reward == pytest.approx(-0.01)
    assert invalid_sell_info["invalid_action"] is True


def test_reset_and_action_sequence_are_deterministic(tmp_path):
    env_a = _env(tmp_path)
    env_b = _env(tmp_path)
    obs_a, info_a = env_a.reset(seed=123)
    obs_b, info_b = env_b.reset(seed=123)

    assert info_a["episode_id"] == info_b["episode_id"]
    assert np.allclose(obs_a, obs_b)

    rewards_a = []
    rewards_b = []
    for action in [ACTION_HOLD, ACTION_BUY, ACTION_HOLD, ACTION_SELL]:
        obs_a, reward_a, term_a, trunc_a, info_a = env_a.step(action)
        obs_b, reward_b, term_b, trunc_b, info_b = env_b.step(action)
        rewards_a.append(reward_a)
        rewards_b.append(reward_b)
        assert term_a == term_b
        assert trunc_a == trunc_b
        assert info_a["current_idx"] == info_b["current_idx"]
        assert np.allclose(obs_a, obs_b)

    assert rewards_a == pytest.approx(rewards_b)


def test_environment_rejects_episode_without_required_horizon(tmp_path):
    manifest_path = _write_env_fixture(tmp_path, rows=7)
    env = StomTickTradingEnv(
        StomTickTradingEnvConfig(
            manifest_path=str(manifest_path),
            split="train",
            episode_id="000001_20250103",
            lookback_window=5,
            reward_horizon_seconds=3,
        )
    )

    with pytest.raises(ValueError, match="at least"):
        env.reset()
