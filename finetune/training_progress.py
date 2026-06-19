
"""Progress helpers for long-running STOM Kronos fine-tuning jobs.

The runner writes a small JSON sidecar after every training log line so a web
page can monitor multi-day jobs without waiting for the child process to exit.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


TRAIN_STEP_RE = re.compile(
    r"\[Rank\s+(?P<rank>\d+),\s*Epoch\s+(?P<epoch>\d+)\/(?P<epochs>\d+),\s*"
    r"Step\s+(?P<step>\d+)\/(?P<total_steps>\d+)\]\s*"
    r"LR\s+(?P<lr>[0-9.eE+-]+),\s*Loss:\s*(?P<loss>[0-9.eE+-]+)"
)
VALIDATION_LOSS_RE = re.compile(r"Validation Loss:\s*(?P<validation_loss>[0-9.eE+-]+)")
TOKENIZER_VALIDATION_PROGRESS_RE = re.compile(
    r"Tokenizer validation progress:\s*Step\s+(?P<validation_step>\d+)\/(?P<validation_total_steps>\d+),\s*"
    r"Samples\s+(?P<validation_samples>\d+),\s*Loss:\s*(?P<validation_loss>[0-9.eE+-]+)"
)
BEST_MODEL_RE = re.compile(
    r"Best model saved to\s+(?P<best_model_path>.+?)\s*\(Val Loss:\s*(?P<best_val_loss>[0-9.eE+-]+)\)"
)
TRAIN_DATASET_RE = re.compile(
    r"Train dataset size:\s*(?P<train_dataset_size>\d+),\s*Validation dataset size:\s*(?P<val_dataset_size>\d+)"
)
DATALOADER_RE = re.compile(
    r"Dataloaders created\.\s*Train steps/epoch:\s*(?P<total_steps>\d+),\s*Val steps:\s*(?P<val_steps>\d+)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_training_log_line(line: str) -> Dict[str, Any]:
    """Parse one Kronos training log line into structured progress fields.

    Returns an empty dict when the line is not a known progress/metric line.
    """
    match = TRAIN_STEP_RE.search(line)
    if match:
        data = match.groupdict()
        return {
            "event": "train_step",
            "rank": int(data["rank"]),
            "epoch": int(data["epoch"]),
            "epochs": int(data["epochs"]),
            "step": int(data["step"]),
            "total_steps": int(data["total_steps"]),
            "learning_rate": float(data["lr"]),
            "loss": float(data["loss"]),
        }

    match = VALIDATION_LOSS_RE.search(line)
    if match:
        return {"event": "validation", "validation_loss": float(match.group("validation_loss"))}

    match = TOKENIZER_VALIDATION_PROGRESS_RE.search(line)
    if match:
        return {
            "event": "validation_progress",
            "validation_step": int(match.group("validation_step")),
            "validation_total_steps": int(match.group("validation_total_steps")),
            "validation_samples": int(match.group("validation_samples")),
            "validation_loss": float(match.group("validation_loss")),
        }

    match = BEST_MODEL_RE.search(line)
    if match:
        return {
            "event": "best_model",
            "best_model_path": match.group("best_model_path").strip(),
            "best_val_loss": float(match.group("best_val_loss")),
        }

    match = TRAIN_DATASET_RE.search(line)
    if match:
        return {
            "event": "dataset_size",
            "train_dataset_size": int(match.group("train_dataset_size")),
            "val_dataset_size": int(match.group("val_dataset_size")),
        }

    match = DATALOADER_RE.search(line)
    if match:
        return {
            "event": "dataloader_ready",
            "total_steps": int(match.group("total_steps")),
            "val_steps": int(match.group("val_steps")),
        }

    if "Training finished. Summary file saved." in line:
        return {"event": "summary_saved"}

    return {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class TrainingProgressTracker:
    """Maintain and persist one stage's training progress JSON sidecar."""

    spec: Mapping[str, Any]
    progress_path: Path
    stdout_path: Path
    stderr_path: Path
    manifest_path: Path
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: str = field(default_factory=utc_now)
    status: str = "created"
    pid: Optional[int] = None
    last_line: str = ""
    current_epoch: int = 0
    epochs: int = 0
    current_step: int = 0
    total_steps: int = 0
    val_steps: int = 0
    last_loss: Optional[float] = None
    last_learning_rate: Optional[float] = None
    last_validation_loss: Optional[float] = None
    best_val_loss: Optional[float] = None
    best_model_path: Optional[str] = None
    train_dataset_size: Optional[int] = None
    val_dataset_size: Optional[int] = None
    validation_step: int = 0
    validation_total_steps: int = 0
    validation_samples: int = 0
    phase: str = "created"
    returncode: Optional[int] = None

    def start(self, pid: Optional[int] = None) -> Dict[str, Any]:
        self.pid = pid
        self.status = "running"
        self.phase = "running"
        return self.write()

    def observe_line(self, line: str) -> Dict[str, Any]:
        self.last_line = line.rstrip("\r\n")
        parsed = parse_training_log_line(line)
        event = parsed.get("event")
        if event == "train_step":
            self.current_epoch = parsed["epoch"]
            self.epochs = parsed["epochs"]
            self.current_step = parsed["step"]
            self.total_steps = parsed["total_steps"]
            self.last_learning_rate = parsed["learning_rate"]
            self.last_loss = parsed["loss"]
            self.phase = "training"
        elif event == "validation":
            self.last_validation_loss = parsed["validation_loss"]
            self.phase = "validation_complete"
        elif event == "validation_progress":
            self.validation_step = parsed["validation_step"]
            self.validation_total_steps = parsed["validation_total_steps"]
            self.validation_samples = parsed["validation_samples"]
            self.last_validation_loss = parsed["validation_loss"]
            self.phase = "validation"
        elif event == "best_model":
            self.best_val_loss = parsed["best_val_loss"]
            self.best_model_path = parsed["best_model_path"]
            self.phase = "checkpoint"
        elif event == "dataset_size":
            self.train_dataset_size = parsed["train_dataset_size"]
            self.val_dataset_size = parsed["val_dataset_size"]
        elif event == "dataloader_ready":
            self.total_steps = parsed["total_steps"]
            self.val_steps = parsed["val_steps"]
        return self.write(last_event=parsed or None)

    def finish(self, returncode: int) -> Dict[str, Any]:
        self.returncode = returncode
        self.status = "ok" if returncode == 0 else "failed"
        self.phase = "completed" if returncode == 0 else "failed"
        return self.write()

    def fail_before_start(self, error: str) -> Dict[str, Any]:
        self.status = "failed"
        self.phase = "failed"
        self.last_line = error
        self.returncode = -1
        return self.write(extra={"error": error})

    def write(self, last_event: Optional[Mapping[str, Any]] = None, extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.snapshot(last_event=last_event)
        if extra:
            payload.update(dict(extra))
        self.progress_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def snapshot(self, last_event: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        elapsed_seconds = max(0.0, (datetime.now(timezone.utc) - self.started_at).total_seconds())
        batch_size = _safe_int(self.spec.get("env", {}).get("KRONOS_BATCH_SIZE"), default=1)
        world_size = _safe_int(self.spec.get("env", {}).get("WORLD_SIZE"), default=1) or 1
        stage_count = max(1, _safe_int(self.spec.get("stage_count"), default=1))
        stage_index = min(stage_count, max(1, _safe_int(self.spec.get("stage_index"), default=1)))
        total_steps = max(0, self.total_steps)
        epochs = max(1, self.epochs or _safe_int(self.spec.get("env", {}).get("KRONOS_EPOCHS"), default=1))
        current_epoch = max(1, self.current_epoch or 1)
        current_step = max(0, self.current_step)
        if total_steps > 0:
            completed_steps = min((current_epoch - 1) * total_steps + current_step, total_steps * epochs)
            stage_fraction = completed_steps / float(total_steps * epochs)
        else:
            completed_steps = 0
            stage_fraction = 0.0
        validation_fraction = 0.0
        if self.validation_total_steps > 0:
            validation_fraction = min(1.0, max(0.0, self.validation_step / float(self.validation_total_steps)))
            # Tokenizer validation starts after the train loop has completed.
            # Reserve the final 2% of the stage for validation so long-running
            # validation no longer appears frozen at the last training log line.
            stage_fraction = max(stage_fraction, 0.98 + 0.02 * validation_fraction)
        stage_fraction = max(0.0, min(1.0, stage_fraction))
        if self.status == "dry_run":
            overall_fraction = 0.0
        else:
            overall_fraction = ((stage_index - 1) + stage_fraction) / float(stage_count)
        overall_fraction = max(0.0, min(1.0, overall_fraction))
        steps_per_second = completed_steps / elapsed_seconds if elapsed_seconds > 0 and completed_steps > 0 else 0.0
        samples_per_second = steps_per_second * batch_size * world_size
        eta_seconds: Optional[float]
        if self.status == "running" and stage_fraction > 0 and elapsed_seconds > 0:
            eta_seconds = max(0.0, elapsed_seconds * (1.0 - stage_fraction) / stage_fraction)
        else:
            eta_seconds = None

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "created_at": self.created_at,
            "updated_at": utc_now(),
            "status": self.status,
            "returncode": self.returncode,
            "pid": self.pid,
            "run_name": self.spec.get("run_name"),
            "horizon": self.spec.get("horizon"),
            "mode": self.spec.get("mode"),
            "train_stage": self.spec.get("train_stage"),
            "requested_train_stage": self.spec.get("requested_train_stage", self.spec.get("train_stage")),
            "sample_stage": self.spec.get("sample_stage"),
            "dataset_dir": self.spec.get("dataset_dir"),
            "target_train_samples": self.spec.get("target_train_samples"),
            "target_val_samples": self.spec.get("target_val_samples"),
            "stage": {
                "index": stage_index,
                "count": stage_count,
                "name": self.spec.get("train_stage"),
                "percent": round(stage_fraction * 100.0, 4),
                "overall_percent": round(overall_fraction * 100.0, 4),
            },
            "progress": {
                "phase": self.phase,
                "epoch": self.current_epoch,
                "epochs": self.epochs or epochs,
                "step": self.current_step,
                "total_steps": self.total_steps,
                "completed_steps": completed_steps,
                "stage_fraction": stage_fraction,
                "overall_fraction": overall_fraction,
                "validation_step": self.validation_step,
                "validation_total_steps": self.validation_total_steps,
                "validation_samples": self.validation_samples,
                "validation_fraction": validation_fraction,
            },
            "metrics": {
                "last_loss": self.last_loss,
                "last_learning_rate": self.last_learning_rate,
                "last_validation_loss": self.last_validation_loss,
                "best_val_loss": self.best_val_loss,
                "best_model_path": self.best_model_path,
            },
            "dataset": {
                "train_dataset_size": self.train_dataset_size,
                "val_dataset_size": self.val_dataset_size,
                "val_steps": self.val_steps,
            },
            "timing": {
                "started_at": self.started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "elapsed_seconds": elapsed_seconds,
                "eta_seconds": eta_seconds,
                "steps_per_second": steps_per_second,
                "samples_per_second": samples_per_second,
            },
            "paths": {
                "progress": str(self.progress_path),
                "stdout_log": str(self.stdout_path),
                "stderr_log": str(self.stderr_path),
                "manifest": str(self.manifest_path),
            },
            "last_line": self.last_line,
        }
        if last_event:
            payload["last_event"] = dict(last_event)
        return payload


def build_dry_run_progress(
    spec: Mapping[str, Any],
    progress_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    manifest_path: Path,
) -> Dict[str, Any]:
    tracker = TrainingProgressTracker(
        spec=spec,
        progress_path=progress_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        manifest_path=manifest_path,
        status="dry_run",
    )
    tracker.status = "dry_run"
    return tracker.write()
