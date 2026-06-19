import pytest

from stom_rl.participant_pressure_features import (
    COL_BID_TOTAL,
    COL_BUY_AMOUNT,
    COL_TRADE_STRENGTH,
    ParticipantPressureError,
    build_participant_pressure_readiness,
    compute_participant_pressure_features,
)
from tests.fixtures.stom_opening_rl import opening_orderbook_frame


def test_participant_proxy_schema_records_available_and_missing_sources(tmp_path):
    frame = opening_orderbook_frame(symbol="000250", session="20250103")

    payload = build_participant_pressure_readiness(
        frame,
        output_dir=tmp_path / "participant",
        decision_second=3,
    )

    assert payload["artifact_type"] == "participant_pressure_readiness"
    assert (tmp_path / "participant" / "participant_pressure_readiness_summary.json").is_file()
    assert payload["proxy_availability"]["trade_strength"] == "available"
    assert payload["proxy_availability"]["bid_depth_imbalance"] == "available"
    assert payload["proxy_availability"]["participant_proxy_pressure"] == "available"
    assert payload["proxy_availability"]["transaction_value_surge"] == "available"
    assert payload["proxy_availability"]["signed_amount_persistence"] == "available"
    assert payload["proxy_availability"]["foreign_net_buy"] == "missing"
    assert payload["proxy_availability"]["institution_net_buy"] == "missing"
    assert payload["proxy_availability"]["program_net_buy"] == "missing"
    assert payload["computed_features"]["foreign_net_buy"] is None
    assert payload["computed_features"]["institution_net_buy"] is None
    assert payload["computed_features"]["program_net_buy"] is None
    assert payload["computed_features"]["participant_proxy_pressure"] > 0.0
    assert payload["computed_features"]["transaction_value_surge"] == payload["computed_features"]["transaction_value_sum"]
    assert payload["computed_features"]["signed_amount_persistence"] == payload["computed_features"]["signed_amount_ratio"]
    assert {
        "participant_proxy_pressure",
        "transaction_value_surge",
        "signed_amount_persistence",
    } <= {spec["name"] for spec in payload["feature_schema"]}
    for spec in payload["feature_schema"]:
        assert spec["feature_group"]
        assert spec["source_column"]
        assert spec["available_at_decision_second"] in {"required", "optional"}
        assert spec["lookback"] >= 0
        assert spec["missing_policy"] in {"fail_closed", "not_causal_at_decision"}


def test_participant_proxy_features_do_not_use_future_rows():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")
    changed_future = frame.copy()
    changed_future.loc[changed_future.index > 2, COL_TRADE_STRENGTH] = 999.0
    changed_future.loc[changed_future.index > 2, COL_BUY_AMOUNT] = 99_000_000.0
    changed_future.loc[changed_future.index > 2, COL_BID_TOTAL] = 99_000.0

    original = compute_participant_pressure_features(frame, decision_second=2)
    changed = compute_participant_pressure_features(changed_future, decision_second=2)

    assert original == changed
    assert original["rows_used"] == 3
    assert original["trade_strength"] == frame[COL_TRADE_STRENGTH].iloc[2]
    assert original["foreign_net_buy"] is None


def test_participant_proxy_rejects_out_of_range_decision_second():
    frame = opening_orderbook_frame(symbol="000250", session="20250103")

    with pytest.raises(ParticipantPressureError, match="decision_second"):
        compute_participant_pressure_features(frame, decision_second=len(frame))
