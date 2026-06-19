import json

import pytest

from stom_rl.opening_30m_rl_manifest import (
    OpeningEpisodeManifestConfig,
    build_opening_episode_manifest,
)
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames


def test_opening_manifest_writes_train_val_test_artifacts(tmp_path):
    frames = build_opening_fixture_frames()
    out_dir = tmp_path / "opening_manifest"

    payload = build_opening_episode_manifest(
        frames,
        OpeningEpisodeManifestConfig(
            output_dir=out_dir,
            split_sessions={
                "train": ("20250103",),
                "val": ("20250106",),
                "test": ("20250107",),
            },
        ),
    )

    first = payload["episodes"][0]
    assert payload["artifact_type"] == "opening_30m_episode_manifest"
    assert payload["summary"]["episode_count"] == 3
    assert payload["summary"]["split_validation"]["overlap_count"] == 0
    assert payload["summary"]["split_validation"]["chronological_train_val_test"] is True
    assert first["symbol"] == "000250"
    assert first["session"] == "20250103"
    assert first["episode_id"] == "000250_20250103"
    assert first["split"] == "train"
    assert first["time_start"] == "090000"
    assert first["time_end"] == "093000"
    assert first["row_count"] == 6
    assert first["quote_coverage"] == 1.0
    assert first["stage_evidence_json"].endswith("opening_episode_manifest_summary.json")
    assert first["source_csv"].endswith("opening_episode_manifest.csv")
    assert (out_dir / "opening_episode_manifest.json").is_file()
    assert (out_dir / "opening_episode_manifest.csv").is_file()
    assert (out_dir / "opening_episode_manifest_summary.json").is_file()
    saved = json.loads((out_dir / "opening_episode_manifest.json").read_text(encoding="utf-8-sig"))
    assert saved["episodes"][2]["symbol"] == "000660"
    assert saved["episodes"][2]["quote_coverage"] < 1.0


def test_opening_manifest_refuses_overlapping_sessions(tmp_path):
    out_dir = tmp_path / "overlap_manifest"

    with pytest.raises(ValueError, match="overlap"):
        build_opening_episode_manifest(
            build_opening_fixture_frames(),
            OpeningEpisodeManifestConfig(
                output_dir=out_dir,
                split_sessions={
                    "train": ("20250103",),
                    "val": ("20250103",),
                    "test": ("20250107",),
                },
            ),
        )

    assert not out_dir.exists()
