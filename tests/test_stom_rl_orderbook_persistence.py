from stom_rl.orderbook_persistence import (
    COL_ASK_TOTAL,
    COL_BID_TOTAL,
    COL_BUY_AMOUNT,
    COL_PRICE,
    COL_SELL_AMOUNT,
    COL_TRADE_STRENGTH,
    REQUIRED_SCORE_COMPONENTS,
    build_orderbook_persistence_score,
    write_orderbook_persistence_artifact,
)
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def test_orderbook_persistence_score_prefers_sustained_bid_pressure(tmp_path):
    strong = opening_orderbook_frame(symbol="000250", session="20250103")
    weak = strong.copy()
    weak[COL_BID_TOTAL] = 600.0
    weak[COL_ASK_TOTAL] = 2400.0
    weak[COL_TRADE_STRENGTH] = 80.0
    weak[COL_BUY_AMOUNT] = 500_000.0
    weak[COL_SELL_AMOUNT] = 1_800_000.0

    strong_score = build_orderbook_persistence_score(strong, decision_second=5)
    weak_score = build_orderbook_persistence_score(weak, decision_second=5)

    assert set(strong_score["components"]) == set(REQUIRED_SCORE_COMPONENTS)
    assert strong_score["feature_groups"]["orderbook_imbalance"] == [
        "bid_ask_depth_imbalance",
        "microprice_pressure",
        "spread_penalty",
    ]
    assert strong_score["score"] > weak_score["score"]
    assert strong_score["components"]["bid_ask_depth_imbalance"] > weak_score["components"]["bid_ask_depth_imbalance"]
    assert strong_score["components"]["bid_depth_persistence"] > weak_score["components"]["bid_depth_persistence"]
    assert strong_score["components"]["signed_flow_persistence"] > weak_score["components"]["signed_flow_persistence"]

    artifact = write_orderbook_persistence_artifact(
        strong,
        output_dir=tmp_path / "score",
        decision_second=5,
    )
    assert artifact["artifact_type"] == "orderbook_persistence_score"
    assert (tmp_path / "score" / "orderbook_persistence_score_summary.json").is_file()


def test_overheat_score_is_causal_and_componentized(tmp_path):
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    changed_future = frame.copy()
    frame.loc[1, COL_PRICE] = 1120.0
    frame.loc[3, COL_PRICE] = 1002.0
    changed_future.loc[1, COL_PRICE] = 1120.0
    changed_future.loc[3, COL_PRICE] = 1002.0
    changed_future.loc[changed_future.index > 3, COL_PRICE] = 1600.0

    original = build_orderbook_persistence_score(frame, decision_second=3)
    changed = build_orderbook_persistence_score(changed_future, decision_second=3)

    assert original["components"] == changed["components"]
    assert original["components"]["overheat_penalty"] > 0.0
    assert original["components"]["upper_wick_ratio"] > 2.0
    assert original["feature_groups"]["overheat_upper_wick"] == [
        "overheat_penalty",
        "upper_wick_ratio",
        "pullback_reacceleration",
    ]
    assert "component_values" in original["artifact_fields"]
    assert "feature_groups" in original["artifact_fields"]
    assert original["rows_used"] == 4
