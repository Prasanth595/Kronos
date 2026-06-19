import json
from pathlib import Path

from stom_rl.opening_30m_rl_artifacts import write_opening_eval_artifacts
from stom_rl.opening_30m_rl_baselines import OpeningBaselineConfig, evaluate_opening_baselines
from tests.fixtures.stom_opening_rl import build_opening_fixture_frames


def _training_payload(tmp_path):
    return {
        "artifact_type": "opening_30m_training_stage",
        "status": "skipped_sb3_unavailable",
        "algorithm": "DQN",
        "seed": 123,
        "total_timesteps": 8,
        "fixed_entry_exit_only": True,
        "train_episode_ids": ["000250_20250103", "005930_20250106"],
        "eval_episode_ids": ["000660_20250107"],
        "model_files": {},
        "evaluation": [
            {"episode_id": "000660_20250107", "reward": 0.0, "steps": 0, "trade_count": 0},
        ],
        "artifacts": {"summary_json": str(tmp_path / "training_summary.json")},
        "strategy_context": {"is_live_ready": False, "is_profit_model": False},
    }


def test_opening_eval_writes_dashboard_compatible_artifacts(tmp_path):
    baseline = evaluate_opening_baselines(build_opening_fixture_frames(), OpeningBaselineConfig())

    payload = write_opening_eval_artifacts(
        output_dir=tmp_path / "eval",
        training_payload=_training_payload(tmp_path),
        baseline_payload=baseline,
        source_manifest_path=Path("manifest.json"),
        seed=123,
        cost_bps=23.0,
    )

    assert payload["artifact_type"] == "opening_30m_eval_artifacts"
    for name in [
        "summary_json",
        "summary_csv",
        "actions_csv",
        "trades_csv",
        "episodes_csv",
        "baseline_csv",
        "diagnostics_json",
        "live_events_jsonl",
    ]:
        assert Path(payload["artifacts"][name]).is_file()
    summary = json.loads(Path(payload["artifacts"]["summary_json"]).read_text(encoding="utf-8"))
    assert summary["summary"]["seed"] == 123
    assert summary["summary"]["cost_bps"] == 23.0
    assert summary["summary"]["train_episode_ids"] == ["000250_20250103", "005930_20250106"]
    assert summary["summary"]["eval_episode_ids"] == ["000660_20250107"]


def test_opening_artifacts_do_not_emit_profit_claim_fields(tmp_path):
    payload = write_opening_eval_artifacts(
        output_dir=tmp_path / "eval",
        training_payload=_training_payload(tmp_path),
        baseline_payload=evaluate_opening_baselines(build_opening_fixture_frames(), OpeningBaselineConfig()),
        source_manifest_path=Path("manifest.json"),
        seed=123,
        cost_bps=23.0,
    )

    raw = json.loads(Path(payload["artifacts"]["summary_json"]).read_text(encoding="utf-8"))

    def walk_keys(value):
        if isinstance(value, dict):  # noqa: IF_VARIANT_OK - recursive JSON tree walker
            for key, nested in value.items():
                yield key
                yield from walk_keys(nested)
        elif isinstance(value, list):
            for item in value:
                yield from walk_keys(item)

    forbidden = [key for key in walk_keys(raw) if "profit" in key.lower() and key != "is_profit_model"]
    assert forbidden == []
