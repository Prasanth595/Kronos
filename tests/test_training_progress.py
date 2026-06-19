
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = REPO_ROOT / "finetune"
if str(FINETUNE_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_DIR))

from training_progress import TrainingProgressTracker, parse_training_log_line  # noqa: E402


def test_parse_training_log_line_extracts_step_and_losses():
    line = "[Rank 0, Epoch 1/2, Step 1000/4701721] LR 0.000123, Loss: 1.2345"

    parsed = parse_training_log_line(line)
    validation = parse_training_log_line("Validation Loss: 0.4321")
    validation_progress = parse_training_log_line(
        "[Rank 0] Tokenizer validation progress: Step 10/100, Samples 640, Loss: 0.5432"
    )
    best = parse_training_log_line("Best model saved to C:/tmp/best_model (Val Loss: 0.3210)")

    assert parsed == {
        "event": "train_step",
        "rank": 0,
        "epoch": 1,
        "epochs": 2,
        "step": 1000,
        "total_steps": 4701721,
        "learning_rate": 0.000123,
        "loss": 1.2345,
    }
    assert validation["validation_loss"] == 0.4321
    assert validation_progress == {
        "event": "validation_progress",
        "validation_step": 10,
        "validation_total_steps": 100,
        "validation_samples": 640,
        "validation_loss": 0.5432,
    }
    assert best["best_val_loss"] == 0.3210
    assert best["best_model_path"] == "C:/tmp/best_model"


def test_training_progress_tracker_writes_stage_and_overall_progress(tmp_path):
    spec = {
        "run_name": "unit_run",
        "horizon": 60,
        "mode": "full",
        "train_stage": "predictor",
        "requested_train_stage": "both",
        "stage_index": 2,
        "stage_count": 2,
        "dataset_dir": "processed_datasets",
        "target_train_samples": 200,
        "target_val_samples": 40,
        "sample_stage": None,
        "env": {"KRONOS_BATCH_SIZE": "4", "WORLD_SIZE": "1", "KRONOS_EPOCHS": "1"},
    }
    progress_path = tmp_path / "logs" / "predictor.progress.json"
    tracker = TrainingProgressTracker(
        spec=spec,
        progress_path=progress_path,
        stdout_path=tmp_path / "logs" / "predictor.stdout.log",
        stderr_path=tmp_path / "logs" / "predictor.stderr.log",
        manifest_path=tmp_path / "run_manifest.json",
    )

    tracker.start(pid=1234)
    tracker.observe_line("[Rank 0] Train dataset size: 200, Validation dataset size: 40")
    payload = tracker.observe_line("[Rank 0, Epoch 1/1, Step 25/100] LR 0.000100, Loss: 0.5000")
    validation_payload = tracker.observe_line(
        "[Rank 0] Tokenizer validation progress: Step 5/10, Samples 20, Loss: 0.4500"
    )
    tracker.observe_line("Validation Loss: 0.4000")
    final_payload = json.loads(progress_path.read_text(encoding="utf-8"))

    assert payload["status"] == "running"
    assert payload["stage"]["percent"] == 25.0
    assert payload["stage"]["overall_percent"] == 62.5
    assert validation_payload["progress"]["phase"] == "validation"
    assert validation_payload["progress"]["validation_fraction"] == 0.5
    assert validation_payload["stage"]["percent"] == 99.0
    assert validation_payload["stage"]["overall_percent"] == 99.5
    assert payload["timing"]["samples_per_second"] >= 0
    assert final_payload["dataset"]["train_dataset_size"] == 200
    assert final_payload["metrics"]["last_validation_loss"] == 0.4


def test_dry_run_progress_does_not_look_half_complete(tmp_path):
    spec = {
        "run_name": "unit_run",
        "horizon": 60,
        "mode": "smoke",
        "train_stage": "predictor",
        "requested_train_stage": "both",
        "stage_index": 2,
        "stage_count": 2,
        "sample_stage": None,
        "env": {"KRONOS_BATCH_SIZE": "1", "WORLD_SIZE": "1", "KRONOS_EPOCHS": "1"},
    }
    tracker = TrainingProgressTracker(
        spec=spec,
        progress_path=tmp_path / "predictor.progress.json",
        stdout_path=tmp_path / "predictor.stdout.log",
        stderr_path=tmp_path / "predictor.stderr.log",
        manifest_path=tmp_path / "run_manifest.json",
        status="dry_run",
    )

    payload = tracker.write()

    assert payload["stage"]["percent"] == 0.0
    assert payload["stage"]["overall_percent"] == 0.0
