from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = PROJECT_ROOT / "finetune"


def test_predictor_handoff_applies_safe_overrides(tmp_path, monkeypatch):
    import sys

    if str(FINETUNE_DIR) not in sys.path:
        sys.path.insert(0, str(FINETUNE_DIR))

    from predictor_handoff import apply_predictor_handoff_overrides

    handoff_path = tmp_path / "predictor_handoff_overrides.json"
    handoff_path.write_text(
        '{"enabled": true, "batch_size": 16, "num_workers": 2, "note": "ignored"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("KRONOS_PREDICTOR_HANDOFF_OVERRIDES", str(handoff_path))
    config = {"save_path": str(tmp_path), "batch_size": 4, "num_workers": 0}

    result = apply_predictor_handoff_overrides(config)

    assert config["batch_size"] == 16
    assert config["num_workers"] == 2
    assert result["applied"] == {"batch_size": 16, "num_workers": 2}
    assert result["ignored"] == {"note": "ignored"}
    assert config["predictor_handoff_overrides"]["exists"] is True


def test_predictor_handoff_rejects_invalid_batch_size(tmp_path, monkeypatch):
    import sys

    if str(FINETUNE_DIR) not in sys.path:
        sys.path.insert(0, str(FINETUNE_DIR))

    from predictor_handoff import apply_predictor_handoff_overrides

    handoff_path = tmp_path / "predictor_handoff_overrides.json"
    handoff_path.write_text('{"batch_size": 0}', encoding="utf-8")
    monkeypatch.setenv("KRONOS_PREDICTOR_HANDOFF_OVERRIDES", str(handoff_path))

    with pytest.raises(ValueError, match="batch_size"):
        apply_predictor_handoff_overrides({"save_path": str(tmp_path), "batch_size": 4})
