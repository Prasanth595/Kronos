import pytest

from stom_rl.opening_30m_rl_baselines import (
    OpeningBaselineConfig,
    evaluate_opening_baselines,
)
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def test_same_decision_ts_imb_baseline_uses_marketable_fills_and_23bp():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")

    payload = evaluate_opening_baselines(
        [frame],
        OpeningBaselineConfig(decision_index=0, cost_bps=23.0),
    )

    ts_imb = next(row for row in payload["rows"] if row["policy"] == "ts_imb_same_decision_tp5_sl1_time")
    assert ts_imb["is_reinforcement_learning"] is False
    assert ts_imb["cost_bps"] == 23.0
    assert ts_imb["entry_price"] == pytest.approx(frame["매도호가1"].iloc[0])
    assert ts_imb["exit_price"] == pytest.approx(frame["매수호가1"].iloc[-1])
    expected_net = (frame["매수호가1"].iloc[-1] / frame["매도호가1"].iloc[0] - 1.0) * 100.0 - 0.23
    assert ts_imb["net_return_pct"] == pytest.approx(expected_net)
    assert payload["summary"]["baseline_delta_inputs"]["no_trade"] == 0.0
    assert "buy_and_hold" in payload["summary"]["baseline_delta_inputs"]


def test_opening_rule_baseline_is_not_reinforcement_learning():
    payload = evaluate_opening_baselines(
        [opening_orderbook_frame(symbol="000250", session="20250103")],
        OpeningBaselineConfig(),
    )

    assert payload["artifact_type"] == "opening_30m_baseline_comparator"
    assert payload["strategy_context"]["label"] == "RULE BASELINE"
    assert payload["strategy_context"]["is_reinforcement_learning"] is False
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert {row["policy"] for row in payload["rows"]} == {
        "no_trade",
        "buy_and_hold",
        "ts_imb_same_decision_tp5_sl1_time",
    }
    assert all(row["is_reinforcement_learning"] is False for row in payload["rows"])
