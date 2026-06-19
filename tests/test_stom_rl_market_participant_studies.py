import json

from stom_rl.market_participant_studies import (
    build_market_participant_studies,
)
from stom_rl.participant_pressure_features import COL_TRANSACTION_VALUE
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def _frame(symbol: str, session: str, *, amount_scale: float = 1.0):
    frame = opening_orderbook_frame(symbol=symbol, session=session)
    frame[COL_TRANSACTION_VALUE] = frame[COL_TRANSACTION_VALUE].astype(float) * amount_scale
    return frame


def test_value_surge_study_writes_group_counts_and_forward_returns(tmp_path):
    frames = [
        _frame("000250", "20250103", amount_scale=1.0),
        _frame("000250", "20250106", amount_scale=10000.0),
        _frame("000250", "20250107", amount_scale=1.5),
    ]

    payload = build_market_participant_studies(frames, output_dir=tmp_path / "study")

    assert payload["artifact_type"] == "market_participant_study"
    assert payload["strategy_context"]["is_reinforcement_learning"] is False
    assert payload["strategy_context"]["is_live_ready"] is False
    assert payload["strategy_context"]["is_profit_model"] is False
    assert payload["config"]["absolute_amount_threshold_krw"] == 100_000_000_000.0
    assert payload["config"]["amount_multiples"] == [2.0, 3.0, 5.0, 10.0]
    assert payload["summary"]["forward_return_columns"] == [
        "forward_1_session_return_pct",
        "forward_3_session_return_pct",
        "forward_5_session_return_pct",
        "forward_20_session_return_pct",
    ]
    assert payload["surge_groups"]["absolute_ge_100b_krw"]["episode_count"] == 1
    assert "baseline_policy" in payload["surge_groups"]["absolute_ge_100b_krw"]
    assert (tmp_path / "study" / "market_participant_study_summary.json").is_file()
    assert (tmp_path / "study" / "market_participant_study_episodes.csv").is_file()

    saved = json.loads((tmp_path / "study" / "market_participant_study_summary.json").read_text(encoding="utf-8"))
    assert saved["surge_groups"]["amount_multiple_ge_2x"]["episode_count"] >= 1


def test_upper_wick_study_marks_missing_flow_proxies_without_zero_fill(tmp_path):
    frame = _frame("000250", "20250103")
    future_changed = frame.copy()
    frame.loc[1, "현재가"] = 1120.0
    frame.loc[3, "현재가"] = 1002.0
    future_changed.loc[1, "현재가"] = 1120.0
    future_changed.loc[3, "현재가"] = 1002.0
    future_changed.loc[future_changed.index > 3, "현재가"] = 1600.0

    original = build_market_participant_studies([frame], output_dir=tmp_path / "original", decision_second=3)
    changed = build_market_participant_studies([future_changed], output_dir=tmp_path / "changed", decision_second=3)

    assert original["upper_wick_study"]["upper_wick_rule"] == "upper_wick > body * 2"
    assert original["upper_wick_study"]["upper_wick_count"] == 1
    assert changed["upper_wick_study"] == original["upper_wick_study"]
    for row in original["proxy_strata"]:
        assert row["status"] == "proxy_unavailable"
        assert row["episode_count"] == original["summary"]["episode_count"]
        assert row["net_buy_sum"] is None
    assert original["verdict"] == "NO-GO_SAMPLE"
