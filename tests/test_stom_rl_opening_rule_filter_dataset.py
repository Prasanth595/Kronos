import pytest

from stom_rl.opening_30m_rl_oos_split import OosSplitError, build_oos_split_manifest
from stom_rl.opening_30m_rule_filter_contract import ACTION_TAKE, RuleFilterConfig
from stom_rl.opening_30m_rule_filter_dataset import build_rule_filter_dataset
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames


def _split():
    return build_oos_split_manifest({"train": ["20250103"], "validation": ["20250106"], "oos": ["20250107"]})


def test_rule_filter_dataset_is_causal_and_preserves_symbols():
    frames = build_opening_fixture_frames()
    split = _split()
    original = build_rule_filter_dataset(frames, split_manifest=split, config=RuleFilterConfig(decision_second=2))
    changed = [frame.copy(deep=True) for frame in frames]
    changed[0].loc[4:, "泥닿껐媛뺣룄"] = 1.0
    changed[0].loc[4:, "留ㅼ닔珥앹옍??"] = 1.0
    mutated = build_rule_filter_dataset(changed, split_manifest=split, config=RuleFilterConfig(decision_second=2))

    assert original["rows"][0]["symbol"] == "000250"
    assert original["rows"][0]["base_action"] == ACTION_TAKE
    assert original["rows"][0]["feature_values"] == mutated["rows"][0]["feature_values"]
    assert "skipped_opportunity_net_return_pct" in original["rows"][0]
    assert original["split_hash"] == split["split_hash"]


def test_rule_filter_dataset_rejects_bad_split_hash():
    split = _split() | {"split_hash": "bad"}
    with pytest.raises(OosSplitError):
        build_rule_filter_dataset(build_opening_fixture_frames(), split_manifest=split, config=RuleFilterConfig())
