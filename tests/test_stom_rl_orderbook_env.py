import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stom_rl.orderbook_rl_env import (
    ACTION_HOLD,
    ACTION_MARKET_BUY,
    ACTION_MARKET_EXIT,
    ORDERBOOK_FEATURE_NAMES,
    OrderbookRlReadinessConfig,
    StomOrderbookRlEnv,
    StomOrderbookRlEnvConfig,
    assess_orderbook_rl_readiness,
    normalize_orderbook_frame,
    seconds_since_open,
)


def _frame(*, future_price: float = 110.0) -> pd.DataFrame:
    prices = [100.0, 102.0, 106.0, 107.0, future_price, future_price + 1.0]
    rows = []
    for sec, price in enumerate(prices):
        rows.append(
            {
                "sec": sec,
                "price": price,
                "ts": 120.0 + sec,
                "buy_val": 1000.0 + sec * 100.0,
                "sell_val": 900.0,
                "buy_qty": 10.0 + sec,
                "sell_qty": 9.0,
                "bid_tot": 600.0 + sec * 10.0,
                "ask_tot": 400.0,
                "bid1": price - 1.0,
                "ask1": price + 1.0,
                "bidq1": 60.0,
                "askq1": 40.0,
            }
        )
    return pd.DataFrame(rows)


def _env(frame: pd.DataFrame | None = None, **overrides):
    return StomOrderbookRlEnv(
        StomOrderbookRlEnvConfig(
            lookback_window=2,
            cost_bps=0.0,
            slippage_bps=0.0,
            invalid_action_penalty=0.01,
            **overrides,
        ),
        frame=_frame() if frame is None else frame,
    )


def test_seconds_since_open_accepts_stom_index_and_timestamp():
    assert seconds_since_open(20250103090005) == 5
    assert seconds_since_open("2025-01-03 09:00:12") == 12


def test_normalize_orderbook_frame_maps_korean_columns():
    raw = pd.DataFrame(
        {
            "index": [20250103090000, 20250103090001],
            "현재가": [100.0, 101.0],
            "체결강도": [120.0, 121.0],
            "초당매수금액": [1000.0, 1100.0],
            "초당매도금액": [900.0, 950.0],
            "초당매수수량": [10.0, 11.0],
            "초당매도수량": [9.0, 9.5],
            "매수총잔량": [600.0, 610.0],
            "매도총잔량": [400.0, 410.0],
            "매수호가1": [99.0, 100.0],
            "매도호가1": [101.0, 102.0],
            "매수잔량1": [60.0, 61.0],
            "매도잔량1": [40.0, 41.0],
        }
    )

    frame = normalize_orderbook_frame(raw)

    assert frame["sec"].tolist() == [0, 1]
    assert frame["price"].tolist() == [100.0, 101.0]
    assert frame["bid1"].tolist() == [99.0, 100.0]
    assert frame["ask1"].tolist() == [101.0, 102.0]


def test_orderbook_env_reset_observation_is_causal_and_fixed_shape():
    env = _env()
    obs, info = env.reset(seed=7)

    assert obs.shape == (len(ORDERBOOK_FEATURE_NAMES),)
    assert env.observation_space.contains(obs)
    assert info["current_idx"] == 1
    assert info["no_future_observation"] is True
    assert info["action_space"][ACTION_MARKET_BUY] == "market_buy"
    assert "spread_rel" in info["feature_columns"]


def test_orderbook_env_market_buy_hold_exit_uses_marketable_fills():
    env = _env()
    env.reset(seed=7)

    _, buy_reward, terminated, truncated, buy_info = env.step(ACTION_MARKET_BUY)
    assert buy_reward > 0.0  # buy at ask=103, mark at next bid=105
    assert buy_info["position_after"] == 1
    assert buy_info["fill_price"] == pytest.approx(103.0)
    assert terminated is False
    assert truncated is False

    _, hold_reward, _, _, hold_info = env.step(ACTION_HOLD)
    assert hold_info["position_after"] == 1
    assert np.isfinite(hold_reward)

    _, exit_reward, _, _, exit_info = env.step(ACTION_MARKET_EXIT)
    assert exit_info["position_after"] == 0
    assert exit_info["fill_price"] == pytest.approx(106.0)
    assert exit_info["realized_trade_return"] == pytest.approx(106.0 / 103.0 - 1.0)
    assert np.isfinite(exit_reward)


def test_orderbook_env_invalid_actions_are_penalized():
    env = _env()
    env.reset(seed=7)

    _, reward, _, _, info = env.step(ACTION_MARKET_EXIT)

    assert reward == pytest.approx(-0.01)
    assert info["invalid_action"] is True
    assert info["invalid_action_count"] == 1
    assert info["position_after"] == 0


def test_orderbook_env_force_closes_open_position_on_terminal_step():
    env = _env(max_episode_steps=1)
    env.reset(seed=7)

    _, _, terminated, _, info = env.step(ACTION_MARKET_BUY)

    assert terminated is True
    assert info["force_closed"] is True
    assert info["position_after"] == 0
    assert info["trade_count"] == 2


def test_observation_at_decision_time_does_not_depend_on_future_rows():
    base = _env(_frame(future_price=110.0))
    changed_future = _env(_frame(future_price=999.0))

    obs_a, _ = base.reset(seed=123)
    obs_b, _ = changed_future.reset(seed=123)

    assert np.allclose(obs_a, obs_b)


def _create_readiness_db(path: Path, *, missing_columns: bool = False) -> None:
    conn = sqlite3.connect(path)
    cols = [
        '"index" INTEGER',
        '"현재가" REAL',
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
    ]
    if not missing_columns:
        cols.append('"매도잔량1" REAL')
    conn.execute(f'CREATE TABLE "000001" ({",".join(cols)})')
    for i in range(8):
        values = [
            20250103090000 + i,
            100.0 + i,
            120.0 + i,
            1000.0 + i,
            900.0,
            10.0 + i,
            9.0,
            600.0 + i,
            400.0,
            99.0 + i,
            101.0 + i,
            60.0,
        ]
        if not missing_columns:
            values.append(40.0)
        conn.execute(
            f'INSERT INTO "000001" VALUES ({",".join("?" for _ in values)})',
            values,
        )
    conn.commit()
    conn.close()


def test_assess_orderbook_rl_readiness_writes_dashboard_artifact(tmp_path):
    db_path = tmp_path / "tick.db"
    _create_readiness_db(db_path)

    payload = assess_orderbook_rl_readiness(
        OrderbookRlReadinessConfig(
            db_path=str(db_path),
            output_dir=str(tmp_path / "run"),
            omx_output_dir=str(tmp_path / "omx"),
            max_symbols=1,
            min_rows_per_episode=5,
            lookback_window=3,
            min_eligible_episodes=1,
        )
    )

    assert payload["summary"]["readiness_status"] == "READY_FOR_MARKETABLE_RL"
    assert payload["summary"]["is_live_ready"] is False
    assert payload["sample_env_smoke"]["passed"] is True
    summary_path = tmp_path / "run" / "orderbook_rl_readiness_summary.json"
    assert summary_path.is_file()
    assert json.loads(summary_path.read_text(encoding="utf-8-sig"))["artifact_type"] == "orderbook_rl_readiness"


def test_assess_orderbook_rl_readiness_flags_missing_orderbook_columns(tmp_path):
    db_path = tmp_path / "tick_missing.db"
    _create_readiness_db(db_path, missing_columns=True)

    payload = assess_orderbook_rl_readiness(
        OrderbookRlReadinessConfig(
            db_path=str(db_path),
            output_dir=str(tmp_path / "run"),
            omx_output_dir=str(tmp_path / "omx"),
            max_symbols=1,
            min_rows_per_episode=5,
            lookback_window=3,
            min_eligible_episodes=1,
            write_artifacts=False,
        )
    )

    assert payload["summary"]["readiness_status"] == "NO-GO_DATA"
    assert payload["missing_column_tables"][0]["missing"] == ["매도잔량1"]
