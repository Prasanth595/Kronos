from stom_rl.opening_30m_rl_oos_split import (
    OosSplitError,
    build_oos_split_manifest,
    validate_oos_split_manifest,
)


def test_oos_split_manifest_is_chronological_and_hashable():
    manifest = build_oos_split_manifest(
        {
            "train": ["20250102", "20250103"],
            "validation": ["20250106"],
            "oos": ["20250107"],
        },
        symbol_sessions={"000020": ["20250102", "20250107"]},
    )

    validate_oos_split_manifest(manifest)

    assert manifest["split_ranges"]["oos"]["start"] == "20250107"
    assert manifest["symbol_session_counts"]["000020"] == 2
    assert isinstance(manifest["split_hash"], str)


def test_oos_split_rejects_overlap_and_row_level_shuffle():
    try:
        build_oos_split_manifest(
            {
                "train": ["20250102", "20250106"],
                "validation": ["20250106"],
                "oos": ["20250107"],
            }
        )
    except OosSplitError as exc:
        assert "overlaps" in str(exc)
    else:
        raise AssertionError("overlapping split should fail")

    try:
        build_oos_split_manifest(
            {"train": ["20250107"], "validation": ["20250106"], "oos": ["20250105"]}
        )
    except OosSplitError as exc:
        assert "chronological" in str(exc)
    else:
        raise AssertionError("non-chronological split should fail")
