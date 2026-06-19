from stom_rl.opening_30m_rl_dataset import build_dataset_artifact
from stom_rl.opening_30m_rl_oos_split import build_oos_split_manifest


def _split_manifest():
    return build_oos_split_manifest(
        {"train": ["20250102"], "validation": ["20250103"], "oos": ["20250106"]}
    )


def test_dataset_artifact_records_features_splits_and_availability():
    artifact = build_dataset_artifact(
        [
            {"symbol": "000020", "session_date": "20250102", "row_count": 30},
            {"symbol": "000040", "session_date": "20250106", "row_count": 40},
        ],
        split_manifest=_split_manifest(),
        features=["trade_strength", "orderbook_imbalance"],
        participant_proxy_availability={"foreign_net_buy": False},
        orderbook_feature_availability={"매수호가1": True},
    )

    assert artifact["row_count"] == 2
    assert artifact["rows"][0]["split"] == "train"
    assert artifact["rows"][1]["split"] == "oos"
    assert artifact["features"] == ["trade_strength", "orderbook_imbalance"]


def test_dataset_artifact_reports_missing_proxy_without_zero_fill():
    artifact = build_dataset_artifact(
        [{"symbol": "000020", "session_date": "20250102", "row_count": 30}],
        split_manifest=_split_manifest(),
        features=["trade_strength"],
        participant_proxy_availability={"foreign_net_buy": False},
        orderbook_feature_availability={"매수호가1": True},
    )

    proxy = artifact["participant_proxy_availability"]["foreign_net_buy"]
    assert proxy["available"] is False
    assert proxy["filled_with_zero"] is False
