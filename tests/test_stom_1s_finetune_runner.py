import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = PROJECT_ROOT / "finetune"
if str(FINETUNE_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_DIR))

from run_stom_1s_finetune import build_run, execute_run, parse_args, sample_stage_budget  # noqa: E402
from model_source import resolve_model_source  # noqa: E402


def _skip_if_torch_cannot_initialize() -> None:
    if os.name == "nt" and os.environ.get("KRONOS_RUN_TORCH_TESTS") != "1":
        pytest.skip(
            "torch-dependent dataset test is opt-in on Windows; set KRONOS_RUN_TORCH_TESTS=1 "
            "in a verified PyTorch environment to run it"
        )
    probe = subprocess.run(
        [sys.executable, "-c", "import torch"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        pytest.skip(
            "torch is installed but cannot be initialized in this environment: "
            f"{(probe.stderr or probe.stdout).strip()}"
        )


def test_resolve_model_source_falls_back_to_hf_identifier_for_missing_local_path():
    source = resolve_model_source(
        "outputs/missing/tokenizer/checkpoints/best_model",
        "NeoQuasar/Kronos-Tokenizer-base",
        "Tokenizer",
    )

    assert source == "NeoQuasar/Kronos-Tokenizer-base"


def test_runner_dry_run_records_reproducible_env(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")

    args = parse_args(
        [
            "--horizon",
            "30",
            "--mode",
            "smoke",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--run-name",
            "unit_smoke",
            "--dry-run",
        ]
    )
    spec = build_run(30, args, "smoke")
    result = execute_run(spec, dry_run=True)

    manifest = Path(result["manifest_path"])
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["status"] == "dry_run"
    assert Path(payload["progress_path"]).exists()
    assert Path(payload["stdout_log"]).exists()
    assert "dry-run only" in Path(payload["stdout_log"]).read_text(encoding="utf-8")
    progress_payload = json.loads(Path(payload["progress_path"]).read_text(encoding="utf-8"))
    assert progress_payload["status"] == "dry_run"
    assert progress_payload["train_stage"] == "predictor"
    assert payload["env_overrides"]["KRONOS_DATASET_PATH"] == str(dataset_dir.resolve())
    assert payload["env_overrides"]["KRONOS_PREDICT_WINDOW"] == "30"
    assert payload["env_overrides"]["KRONOS_USE_COMET"] == "0"
    assert payload["env_overrides"]["KRONOS_DDP_BACKEND"] == "gloo"
    assert payload["env_overrides"]["USE_LIBUV"] == "0"
    assert payload["env_overrides"]["PYTHONUNBUFFERED"] == "1"
    assert payload["env_overrides"]["WORLD_SIZE"] == "1"
    assert payload["env_overrides"]["KRONOS_DISABLE_DDP"] == "1"
    assert payload["command"][-1].endswith("train_predictor.py")


def test_sample_stage_sets_staged_full_training_budget(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")

    args = parse_args(
        [
            "--horizon",
            "60",
            "--mode",
            "full",
            "--sample-stage",
            "expand_200k",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--dry-run",
        ]
    )
    spec = build_run(60, args, "full")

    assert spec["sample_stage"] == "expand_200k"
    assert spec["run_name"] == "stom_1s_grid_pred60_expand_200k"
    assert spec["target_train_samples"] == 200_000
    assert spec["target_val_samples"] == 40_000
    assert spec["env"]["KRONOS_N_TRAIN_ITER"] == "200000"
    assert spec["env"]["KRONOS_N_VAL_ITER"] == "40000"


def test_runner_can_build_tokenizer_stage_and_both_stage_handoff(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")

    args = parse_args(
        [
            "--horizon",
            "60",
            "--mode",
            "smoke",
            "--train-stage",
            "both",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--run-name",
            "official_smoke",
            "--dataset-sample-mode",
            "full_sequential",
            "--dry-run",
        ]
    )

    tokenizer_spec = build_run(60, args, "smoke", train_stage="tokenizer")
    predictor_spec = build_run(60, args, "smoke", train_stage="predictor")

    assert tokenizer_spec["train_stage"] == "tokenizer"
    assert tokenizer_spec["manifest_path"].endswith("tokenizer_run_manifest.json")
    assert tokenizer_spec["command"][-1].endswith("train_tokenizer.py")
    assert tokenizer_spec["env"]["KRONOS_DATASET_SAMPLE_MODE"] == "full_sequential"
    assert tokenizer_spec["env"]["KRONOS_TOKENIZER_VAL_BATCH_SIZE"] == "1"
    assert tokenizer_spec["env"]["KRONOS_TOKENIZER_SAVE_PRE_VAL_CHECKPOINT"] == "1"
    assert predictor_spec["command"][-1].endswith("train_predictor.py")
    assert "KRONOS_TOKENIZER_VAL_BATCH_SIZE" not in predictor_spec["env"]
    assert predictor_spec["env"]["KRONOS_FINETUNED_TOKENIZER_PATH"].endswith(
        "official_smoke\\finetune_tokenizer\\checkpoints\\best_model"
    )
    assert predictor_spec["tokenizer_handoff_source"] == "best_model_expected"


def test_both_stage_can_use_predictor_efficiency_overrides(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")

    args = parse_args(
        [
            "--horizon",
            "60",
            "--mode",
            "full",
            "--train-stage",
            "both",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--run-name",
            "efficiency_handoff",
            "--batch-size",
            "4",
            "--num-workers",
            "0",
            "--predictor-batch-size",
            "16",
            "--predictor-num-workers",
            "2",
            "--dry-run",
        ]
    )

    tokenizer_spec = build_run(60, args, "full", train_stage="tokenizer")
    predictor_spec = build_run(60, args, "full", train_stage="predictor")

    assert tokenizer_spec["env"]["KRONOS_BATCH_SIZE"] == "4"
    assert tokenizer_spec["env"]["KRONOS_TOKENIZER_VAL_BATCH_SIZE"] == "1"
    assert tokenizer_spec["env"]["KRONOS_NUM_WORKERS"] == "0"
    assert predictor_spec["env"]["KRONOS_BATCH_SIZE"] == "16"
    assert predictor_spec["env"]["KRONOS_NUM_WORKERS"] == "2"
    assert predictor_spec["env"]["KRONOS_FINETUNED_TOKENIZER_PATH"].endswith(
        "efficiency_handoff\\finetune_tokenizer\\checkpoints\\best_model"
    )


def test_both_stage_predictor_handoff_falls_back_to_latest_train_model(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")
    latest = (
        tmp_path
        / "outputs"
        / "resume_handoff"
        / "finetune_tokenizer"
        / "checkpoints"
        / "latest_train_model"
    )
    latest.mkdir(parents=True)
    (latest / "model.safetensors").write_bytes(b"weights")

    args = parse_args(
        [
            "--horizon",
            "60",
            "--mode",
            "full",
            "--train-stage",
            "both",
            "--start-stage",
            "predictor",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--run-name",
            "resume_handoff",
            "--dry-run",
        ]
    )

    predictor_spec = build_run(60, args, "full", train_stage="predictor")

    assert predictor_spec["stage_index"] == 2
    assert predictor_spec["stage_count"] == 2
    assert predictor_spec["tokenizer_handoff_source"] == "latest_train_model"
    assert predictor_spec["env"]["KRONOS_FINETUNED_TOKENIZER_PATH"].endswith(
        "resume_handoff\\finetune_tokenizer\\checkpoints\\latest_train_model"
    )


def test_tokenizer_validation_batch_size_can_be_overridden(tmp_path):
    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    (dataset_dir / "train_data.pkl").write_bytes(b"not loaded in dry-run")
    (dataset_dir / "val_data.pkl").write_bytes(b"not loaded in dry-run")

    args = parse_args(
        [
            "--horizon",
            "60",
            "--mode",
            "full",
            "--train-stage",
            "tokenizer",
            "--dataset-dir",
            str(dataset_dir),
            "--output-root",
            str(tmp_path / "outputs"),
            "--tokenizer-batch-size",
            "4",
            "--tokenizer-val-batch-size",
            "2",
            "--dry-run",
        ]
    )

    tokenizer_spec = build_run(60, args, "full", train_stage="tokenizer")

    assert tokenizer_spec["env"]["KRONOS_BATCH_SIZE"] == "4"
    assert tokenizer_spec["env"]["KRONOS_TOKENIZER_VAL_BATCH_SIZE"] == "2"


def test_full_window_sample_stage_uses_known_full_sample_pool():
    assert sample_stage_budget("full_window", 30) == {"train": 75_277_195, "val": 16_275_307}
    assert sample_stage_budget("full_window", 60) == {"train": 73_718_875, "val": 15_938_107}


def test_full_sequential_dataset_uses_requested_index_order(tmp_path, monkeypatch):
    _skip_if_torch_cannot_initialize()
    from dataset import QlibDataset  # noqa: E402

    dataset_dir = tmp_path / "processed_datasets"
    dataset_dir.mkdir()
    frame = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6],
            "high": [1, 2, 3, 4, 5, 6],
            "low": [1, 2, 3, 4, 5, 6],
            "close": [1, 2, 3, 4, 5, 6],
            "vol": [10, 20, 30, 40, 50, 60],
            "amt": [100, 200, 300, 400, 500, 600],
        },
        index=pd.date_range("2026-01-02 09:00:00", periods=6, freq="s"),
    )
    frame.index.name = "datetime"
    payload = {"KR000001_20260102": frame}
    pd.to_pickle(payload, dataset_dir / "train_data.pkl")
    pd.to_pickle(payload, dataset_dir / "val_data.pkl")

    monkeypatch.setenv("KRONOS_DATASET_PATH", str(dataset_dir))
    monkeypatch.setenv("KRONOS_LOOKBACK_WINDOW", "2")
    monkeypatch.setenv("KRONOS_PREDICT_WINDOW", "1")
    monkeypatch.setenv("KRONOS_N_TRAIN_ITER", "3")
    monkeypatch.setenv("KRONOS_DATASET_SAMPLE_MODE", "full_sequential")

    dataset = QlibDataset("train")
    dataset.py_rng.randint = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("random sampler used"))
    first, _ = dataset[0]

    assert len(dataset) == 3
    assert first.shape[0] == 4
