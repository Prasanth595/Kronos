import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from stom_rl.orderbook_rl_env import StomOrderbookRlEnvConfig
from stom_rl.orderbook_sb3_adapter import OrderbookEpisode, StomOrderbookGymEnv


def _frame(rows: int = 16) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sec": list(range(rows)),
            "price": [100.0 + i for i in range(rows)],
            "ts": [120.0 + i for i in range(rows)],
            "buy_val": [1000.0 + i for i in range(rows)],
            "sell_val": [900.0 for _ in range(rows)],
            "buy_qty": [10.0 + i for i in range(rows)],
            "sell_qty": [9.0 for _ in range(rows)],
            "bid_tot": [600.0 + i for i in range(rows)],
            "ask_tot": [400.0 for _ in range(rows)],
            "bid1": [99.0 + i for i in range(rows)],
            "ask1": [101.0 + i for i in range(rows)],
            "bidq1": [60.0 for _ in range(rows)],
            "askq1": [40.0 for _ in range(rows)],
        }
    )


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=False)
    combined = result.stdout + result.stderr
    if result.returncode != 0 and any(
        marker in combined for marker in ["ModuleNotFoundError", "DLL load failed", "WinError 1114", "c10.dll"]
    ):
        pytest.skip(combined)
    return result


def test_orderbook_gym_env_resets_and_steps_with_episode_metadata():
    env = StomOrderbookGymEnv(
        [OrderbookEpisode("000001_20250103", "000001", "20250103", _frame())],
        StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=0.0, max_episode_steps=4),
    )

    obs, info = env.reset(seed=7)
    obs, reward, terminated, truncated, step_info = env.step(1)

    assert env.observation_space.contains(obs)
    assert info["episode_id"] == "000001_20250103"
    assert step_info["symbol"] == "000001"
    assert reward != 0.0
    assert terminated is False
    assert truncated is False


def test_orderbook_gym_env_can_constrain_invalid_actions_to_hold():
    env = StomOrderbookGymEnv(
        [OrderbookEpisode("000001_20250103", "000001", "20250103", _frame())],
        StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=0.0, max_episode_steps=4),
        constrain_invalid_actions=True,
    )

    env.reset(seed=7)
    _, reward, _, _, step_info = env.step(2)  # market_exit while flat -> hold

    assert reward >= 0.0
    assert step_info["policy_action"] == 2
    assert step_info["executed_action"] == 0
    assert step_info["action_remapped"] is True
    assert step_info["invalid_action_prevented"] is True
    assert step_info["invalid_action"] is False
    assert step_info["invalid_action_count"] == 0
    assert step_info["constraint_mode"] == "hold_on_invalid"


def test_orderbook_gym_env_single_entry_exit_contract_blocks_overtrading():
    env = StomOrderbookGymEnv(
        [OrderbookEpisode("000001_20250103", "000001", "20250103", _frame())],
        StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=0.0, max_episode_steps=8),
        single_entry_exit=True,
    )

    env.reset(seed=7)
    _, skip_reward, terminated, _, skip_info = env.step(0)
    assert terminated is True
    assert skip_reward == 0.0
    assert skip_info["semantic_action_name"] == "skip"
    assert skip_info["trade_count"] == 0

    env.reset(seed=7)
    _, buy_reward, terminated, _, buy_info = env.step(1)
    assert terminated is False
    assert buy_reward != 0.0
    assert buy_info["semantic_action_name"] == "enter"
    assert buy_info["trade_count"] == 1

    _, exit_reward, terminated, _, exit_info = env.step(2)
    assert terminated is True
    assert exit_info["semantic_action_name"] == "exit"
    assert exit_info["trade_count"] == 2
    assert exit_reward == pytest.approx(float(exit_reward))


def test_orderbook_gym_env_fixed_entry_exit_only_starts_position_and_only_exits():
    env = StomOrderbookGymEnv(
        [OrderbookEpisode("000001_20250103", "000001", "20250103", _frame())],
        StomOrderbookRlEnvConfig(lookback_window=3, cost_bps=0.0, max_episode_steps=8),
        fixed_entry_exit_only=True,
    )

    obs, info = env.reset(seed=7)
    assert env.action_space.n == 2
    assert env.observation_space.contains(obs)
    assert info["fixed_entry"] is True
    assert info["position_after"] == 1
    assert info["trade_count"] == 1

    _, hold_reward, terminated, _, hold_info = env.step(0)
    assert terminated is False
    assert hold_info["semantic_action_name"] == "hold"
    assert hold_info["policy_action_name"] == "hold"
    assert hold_reward == pytest.approx(float(hold_reward))

    _, exit_reward, terminated, _, exit_info = env.step(1)
    assert terminated is True
    assert exit_info["semantic_action_name"] == "exit"
    assert exit_info["policy_action_name"] == "exit"
    assert exit_info["position_after"] == 0
    assert exit_info["trade_count"] == 2
    assert exit_reward == pytest.approx(float(exit_reward))


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cols = [
        '"index" INTEGER',
        '"현재가" REAL',
        '"등락율" REAL',
        '"체결강도" REAL',
        '"초당매수금액" REAL',
        '"초당매도금액" REAL',
        '"초당매수수량" REAL',
        '"초당매도수량" REAL',
        '"매수총잔량" REAL',
        '"매도총잔량" REAL',
        '"매수호가1" REAL',
        '"매도호가1" REAL',
        '"매수잔량1" REAL',
        '"매도잔량1" REAL',
    ]
    for symbol_idx, symbol in enumerate(["000001", "000002", "000003", "000004"]):
        conn.execute(f'CREATE TABLE "{symbol}" ({",".join(cols)})')
        for session_idx, session in enumerate(["20250103", "20250106", "20250107", "20250108"]):
            base_price = 100.0 + symbol_idx + session_idx
            for sec in range(20):
                price = base_price + sec * (0.2 if session_idx % 2 == 0 else -0.05)
                values = [
                    int(f"{session}0900{sec:02d}"),
                    price,
                    2.5,
                    150.0,
                    1000.0 + sec,
                    800.0,
                    10.0 + sec,
                    8.0,
                    700.0,
                    300.0,
                    price - 0.1,
                    price + 0.1,
                    70.0,
                    30.0,
                ]
                conn.execute(f'INSERT INTO "{symbol}" VALUES ({",".join("?" for _ in values)})', values)
    conn.commit()
    conn.close()


def test_orderbook_dqn_smoke_writes_oos_verdict_artifact(tmp_path):
    db_path = tmp_path / "tick.db"
    out_dir = tmp_path / "out"
    _create_db(db_path)

    result = _run_python(
        f"""
import json
from stom_rl.orderbook_sb3_smoke import OrderbookDqnSmokeConfig, run_orderbook_dqn_smoke
payload = run_orderbook_dqn_smoke(
    OrderbookDqnSmokeConfig(
        db_path={str(db_path)!r},
        output_dir={str(out_dir)!r},
        max_scan_symbols=4,
        train_episodes=4,
        eval_episodes=4,
        min_eval_episodes=2,
        lookback_window=3,
        max_episode_steps=5,
        total_timesteps=16,
        cost_bps=0.0,
        overtrade_penalty=0.001,
        constrain_invalid_actions=True,
        single_entry_exit=True,
        fixed_entry_exit_only=True,
        device="cpu",
    )
)
print(json.dumps({{
    "mode": payload["mode"],
    "artifact_type": payload["artifact_type"],
    "verdict": payload["summary"]["verdict"],
    "eval_episode_count": payload["summary"]["eval_episode_count"],
}}))
"""
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["mode"] == "stom_orderbook_rl_sb3_smoke"
    assert payload["artifact_type"] == "sb3_smoke"
    assert payload["verdict"] in {"GO_CANDIDATE", "NO-GO"}
    assert payload["eval_episode_count"] >= 2
    assert (out_dir / "sb3_smoke_summary.json").is_file()
    assert (out_dir / "orderbook_oos_verdict.json").is_file()
    assert (out_dir / "orderbook_diagnostics.json").is_file()
    assert (out_dir / "dqn_model.zip").is_file()
    summary = json.loads((out_dir / "sb3_smoke_summary.json").read_text(encoding="utf-8-sig"))
    diagnostics = json.loads((out_dir / "orderbook_diagnostics.json").read_text(encoding="utf-8-sig"))
    assert summary["summary"]["overtrade_penalty"] == 0.001
    assert summary["summary"]["constrain_invalid_actions"] is True
    assert summary["summary"]["single_entry_exit"] is True
    assert summary["summary"]["fixed_entry_exit_only"] is True
    assert diagnostics["smallest_fix_selected"] == "fixed_entry_exit_only"
    assert diagnostics["constrain_invalid_actions"] is True
    assert diagnostics["invalid_action_rate"] == 0.0
    assert "action_counts" in diagnostics
    assert "executed_action_counts" in diagnostics
    assert set(diagnostics["action_counts"]).issubset({"hold", "exit"})
