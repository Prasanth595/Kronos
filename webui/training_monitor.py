
"""Filesystem-backed live monitor helpers for STOM Kronos training runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:  # optional dependency: use it when the runtime already has psutil.
    import psutil as _psutil  # type: ignore
except Exception:  # pragma: no cover - exercised through fallback paths.
    _psutil = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOTS: List[Path] = [PROJECT_ROOT / "finetune" / "outputs"]
MAX_LOG_LINES = 1000
MODEL_WEIGHT_SUFFIXES = {".pt", ".pth", ".safetensors", ".ckpt", ".bin"}
TRAIN_STEP_RE = re.compile(
    r"\[Rank (?P<rank>\d+), Epoch (?P<epoch>\d+)/(?P<epochs>\d+), "
    r"Step (?P<step>\d+)/(?P<total_steps>\d+)\]\s+LR "
    r"(?P<learning_rate>[-+0-9.eE]+), Loss: (?P<loss>[-+0-9.eE]+)"
)
STOM_MODEL_FEATURES = ["open", "high", "low", "close", "vol", "amt"]
STOM_TIME_FEATURES = ["minute", "hour", "weekday", "day", "month"]
CPU_TEMPERATURE_LIMIT_C = 95.0
_SYSTEM_STATUS_CACHE: Dict[str, Any] = {"expires_at": 0.0, "payload": None}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"status": "unreadable", "error": str(exc), "path": str(path)}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_run_name(run_name: str) -> str:
    if not run_name or run_name in {".", ".."}:
        raise ValueError("run name is required")
    if any(separator in run_name for separator in ("/", "\\")):
        raise ValueError("run name must be a direct finetune output directory name")
    return run_name


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _latest_mtime(paths: Iterable[Path]) -> float:
    latest = 0.0
    for path in paths:
        latest = max(latest, _file_mtime(path))
    return latest


def _iter_run_dirs() -> Iterable[Path]:
    for root in OUTPUT_ROOTS:
        if not root.exists():
            continue
        for candidate in root.iterdir():
            if candidate.is_dir() and _is_relative_to(candidate, root):
                yield candidate


def _run_artifacts(run_dir: Path) -> Dict[str, List[Path]]:
    logs_dir = run_dir / "logs"
    progress_files = sorted(logs_dir.glob("*.progress.json")) if logs_dir.exists() else []
    manifest_files = sorted(run_dir.glob("*run_manifest.json"))
    log_files = sorted(logs_dir.glob("*.stdout.log")) if logs_dir.exists() else []
    return {"progress": progress_files, "manifest": manifest_files, "log": log_files}


def _summarize_stage(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    stage = payload.get("stage") if isinstance(payload.get("stage"), dict) else {}
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
    paths = payload.get("paths") if isinstance(payload.get("paths"), dict) else {}
    status = payload.get("status", "unknown")
    updated_at = payload.get("updated_at") or payload.get("completed_at") or payload.get("created_at")
    elapsed_seconds = timing.get("elapsed_seconds")
    seconds_since_update = None
    now = datetime.now(timezone.utc)
    updated_dt = _parse_utc_timestamp(updated_at)
    if updated_dt is not None:
        seconds_since_update = max(0.0, (now - updated_dt).total_seconds())
    if status == "running":
        started_dt = _parse_utc_timestamp(timing.get("started_at"))
        if started_dt is not None:
            live_elapsed = max(0.0, (now - started_dt).total_seconds())
            if not isinstance(elapsed_seconds, (int, float)) or live_elapsed > float(elapsed_seconds):
                elapsed_seconds = live_elapsed
    return {
        "source_path": str(source_path),
        "updated_at": updated_at,
        "status": status,
        "run_name": payload.get("run_name"),
        "train_stage": payload.get("train_stage") or stage.get("name"),
        "horizon": payload.get("horizon"),
        "mode": payload.get("mode"),
        "stage_index": stage.get("index"),
        "stage_count": stage.get("count"),
        "stage_percent": stage.get("percent"),
        "overall_percent": stage.get("overall_percent"),
        "epoch": progress.get("epoch"),
        "epochs": progress.get("epochs"),
        "step": progress.get("step"),
        "total_steps": progress.get("total_steps"),
        "phase": progress.get("phase"),
        "validation_step": progress.get("validation_step"),
        "validation_total_steps": progress.get("validation_total_steps"),
        "validation_samples": progress.get("validation_samples"),
        "validation_fraction": progress.get("validation_fraction"),
        "last_loss": (payload.get("metrics") or {}).get("last_loss") if isinstance(payload.get("metrics"), dict) else None,
        "last_validation_loss": (payload.get("metrics") or {}).get("last_validation_loss") if isinstance(payload.get("metrics"), dict) else None,
        "best_val_loss": (payload.get("metrics") or {}).get("best_val_loss") if isinstance(payload.get("metrics"), dict) else None,
        "elapsed_seconds": elapsed_seconds,
        "seconds_since_update": seconds_since_update,
        "eta_seconds": timing.get("eta_seconds"),
        "samples_per_second": timing.get("samples_per_second"),
        "stdout_log": paths.get("stdout_log") or payload.get("stdout_log"),
        "last_line": payload.get("last_line"),
    }


def _manifest_as_stage(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    return {
        "source_path": str(source_path),
        "updated_at": payload.get("completed_at") or payload.get("created_at"),
        "status": payload.get("status", "unknown"),
        "run_name": payload.get("run_name"),
        "train_stage": payload.get("train_stage"),
        "horizon": payload.get("horizon"),
        "mode": payload.get("mode"),
        "stage_index": payload.get("stage_index"),
        "stage_count": payload.get("stage_count"),
        "stage_percent": 100.0 if payload.get("status") == "ok" else 0.0,
        "overall_percent": 100.0 if payload.get("status") == "ok" else 0.0,
        "epoch": None,
        "epochs": None,
        "step": None,
        "total_steps": None,
        "last_loss": None,
        "last_validation_loss": None,
        "best_val_loss": None,
        "elapsed_seconds": payload.get("duration_seconds"),
        "eta_seconds": None,
        "samples_per_second": None,
        "stdout_log": payload.get("stdout_log"),
        "last_line": (payload.get("stdout_tail") or payload.get("stderr_tail") or "")[-500:],
    }


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_path(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def _extract_dataset_run_metadata(artifacts: Dict[str, List[Path]]) -> Dict[str, Any]:
    """Read small run progress/manifest files and collect dataset-related fields."""
    metadata: Dict[str, Any] = {
        "dataset_dir": None,
        "target_train_samples": None,
        "target_val_samples": None,
        "train_dataset_size": None,
        "val_dataset_size": None,
    }
    for source_path in [*artifacts.get("progress", []), *artifacts.get("manifest", [])]:
        payload = _load_json(source_path)
        dataset = payload.get("dataset") if isinstance(payload.get("dataset"), dict) else {}
        env_overrides = payload.get("env_overrides") if isinstance(payload.get("env_overrides"), dict) else {}
        dataset_dir = payload.get("dataset_dir") or env_overrides.get("KRONOS_DATASET_PATH")
        if not metadata["dataset_dir"] and dataset_dir:
            metadata["dataset_dir"] = str(dataset_dir)
        for key in ("target_train_samples", "target_val_samples"):
            if metadata.get(key) is None:
                metadata[key] = _to_int(payload.get(key))
        if metadata["train_dataset_size"] is None:
            metadata["train_dataset_size"] = _to_int(dataset.get("train_dataset_size"))
        if metadata["val_dataset_size"] is None:
            metadata["val_dataset_size"] = _to_int(dataset.get("val_dataset_size"))
    return metadata


def _split_possible_samples(split_counts: Dict[str, Any], min_rows_per_group: Optional[int]) -> Optional[int]:
    rows = _to_int(split_counts.get("rows"))
    groups = _to_int(split_counts.get("groups"))
    if rows is None or groups is None or not min_rows_per_group:
        return None
    return max(0, rows - groups * (min_rows_per_group - 1))


def _summarize_export_split(
    split_name: str,
    report: Dict[str, Any],
    current_targets: Dict[str, Optional[int]],
) -> Dict[str, Any]:
    split_counts = report.get("split_counts") if isinstance(report.get("split_counts"), dict) else {}
    split_sessions = report.get("split_sessions") if isinstance(report.get("split_sessions"), dict) else {}
    counts = split_counts.get(split_name) if isinstance(split_counts.get(split_name), dict) else {}
    sessions = split_sessions.get(split_name) if isinstance(split_sessions.get(split_name), list) else []
    possible_samples = _split_possible_samples(counts, _to_int(report.get("min_rows_per_group")))
    target_key = "train_samples" if split_name == "train" else "val_samples" if split_name == "val" else None
    return {
        "name": split_name,
        "sessions": _to_int(counts.get("sessions")) or len(sessions),
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "groups": _to_int(counts.get("groups")),
        "rows": _to_int(counts.get("rows")),
        "possible_samples": possible_samples,
        "current_target_samples": current_targets.get(target_key) if target_key else None,
    }


def load_dataset_summary(run_dir: Path, artifacts: Optional[Dict[str, List[Path]]] = None) -> Dict[str, Any]:
    """Return compact STOM/Qlib dataset metadata for the live dashboard.

    The full export report includes per-table details and can be large, so this
    function exposes only the range, split, feature, and count fields needed by
    the UI.
    """
    artifacts = artifacts or _run_artifacts(run_dir)
    metadata = _extract_dataset_run_metadata(artifacts)
    dataset_dir = Path(metadata["dataset_dir"]) if metadata.get("dataset_dir") else None
    export_root = dataset_dir.parent if dataset_dir else None
    report_path = export_root / "stom_qlib_export_report.json" if export_root else None
    current_targets = {
        "train_samples": metadata.get("target_train_samples") or metadata.get("train_dataset_size"),
        "val_samples": metadata.get("target_val_samples") or metadata.get("val_dataset_size"),
    }

    if report_path is None or not report_path.exists():
        return {
            "available": False,
            "dataset_dir": _compact_path(dataset_dir),
            "report_path": _compact_path(report_path),
            "current_targets": current_targets,
            "features": STOM_MODEL_FEATURES,
            "time_features": STOM_TIME_FEATURES,
            "message": "STOM Qlib export report was not found for this run.",
        }

    report = _load_json(report_path)
    config = report.get("config") if isinstance(report.get("config"), dict) else {}
    split_sessions = report.get("split_sessions") if isinstance(report.get("split_sessions"), dict) else {}
    all_sessions: List[str] = []
    for split_name in ("train", "val", "test"):
        sessions = split_sessions.get(split_name)
        if isinstance(sessions, list):
            all_sessions.extend(str(session) for session in sessions)

    tables = report.get("tables") if isinstance(report.get("tables"), list) else []
    tables_with_rows = sum(1 for table in tables if _to_int(table.get("written_rows")) and _to_int(table.get("written_rows")) > 0)
    table_count = len(tables) if tables else None
    min_rows_per_group = _to_int(report.get("min_rows_per_group"))
    lookback_window = _to_int(config.get("lookback_window"))
    predict_window = _to_int(config.get("predict_window"))
    sample_window = min_rows_per_group or (
        lookback_window + predict_window + 1
        if lookback_window is not None and predict_window is not None
        else None
    )
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []

    return {
        "available": True,
        "dataset_dir": _compact_path(dataset_dir),
        "report_path": _compact_path(report_path),
        "source_db": config.get("db_path"),
        "freq": config.get("freq"),
        "regularize_1s": bool(config.get("regularize_1s")),
        "price_mode": config.get("price_mode"),
        "horizon_seconds": _to_int(config.get("horizon_seconds")),
        "lookback_window": lookback_window,
        "predict_window": predict_window,
        "sample_window": sample_window,
        "features": STOM_MODEL_FEATURES,
        "time_features": STOM_TIME_FEATURES,
        "range": {
            "session_start": config.get("session_start"),
            "session_end": config.get("session_end"),
            "actual_start": min(all_sessions) if all_sessions else None,
            "actual_end": max(all_sessions) if all_sessions else None,
            "time_start": config.get("time_start"),
            "time_end": config.get("time_end"),
        },
        "counts": {
            "selected_table_count": report.get("selected_table_count"),
            "table_count": table_count,
            "tables_with_rows": tables_with_rows,
            "tables_zero_rows": table_count - tables_with_rows if table_count is not None else None,
            "exported_group_count": _to_int(report.get("exported_group_count")),
            "exported_row_count": _to_int(report.get("exported_row_count")),
            "regularized_groups": _to_int((report.get("grid_summary") or {}).get("regularized_groups"))
            if isinstance(report.get("grid_summary"), dict)
            else None,
            "regularized_inserted_rows": _to_int((report.get("grid_summary") or {}).get("inserted_rows"))
            if isinstance(report.get("grid_summary"), dict)
            else None,
        },
        "splits": {
            split_name: _summarize_export_split(split_name, report, current_targets)
            for split_name in ("train", "val", "test")
        },
        "current_targets": current_targets,
        "warnings": [str(warning) for warning in warnings[:5]],
    }


def list_training_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """List known finetune output runs without reading arbitrary paths."""
    runs: List[Dict[str, Any]] = []
    for run_dir in _iter_run_dirs():
        artifacts = _run_artifacts(run_dir)
        if not artifacts["progress"] and not artifacts["manifest"] and not artifacts["log"]:
            continue
        latest = _latest_mtime(artifacts["progress"] + artifacts["manifest"] + artifacts["log"] + [run_dir])
        status = "unknown"
        overall_percent = None
        stages: List[Dict[str, Any]] = []
        for progress_file in artifacts["progress"]:
            stage = _summarize_stage(_load_json(progress_file), progress_file)
            stages.append(stage)
        if not stages:
            for manifest_file in artifacts["manifest"]:
                stages.append(_manifest_as_stage(_load_json(manifest_file), manifest_file))
        if stages:
            statuses = {str(stage.get("status")) for stage in stages}
            if "running" in statuses:
                status = "running"
            elif "failed" in statuses:
                status = "failed"
            elif statuses and statuses <= {"ok", "dry_run", "recovered"}:
                status = "ok" if "ok" in statuses or "recovered" in statuses else "dry_run"
            elif statuses:
                status = sorted(statuses)[0]
            percents = [stage.get("overall_percent") for stage in stages if isinstance(stage.get("overall_percent"), (int, float))]
            overall_percent = max(percents) if percents else None
        runs.append(
            {
                "name": run_dir.name,
                "path": str(run_dir),
                "status": status,
                "overall_percent": overall_percent,
                "updated_at_epoch": latest,
                "updated_at": datetime.fromtimestamp(latest, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if latest else None,
                "stage_count": len(stages),
            }
        )
    runs.sort(key=lambda item: item.get("updated_at_epoch") or 0, reverse=True)
    return runs[: max(1, min(int(limit), 200))]


def resolve_run_dir(run_name: Optional[str] = None) -> Path:
    if run_name:
        safe_name = _safe_run_name(run_name)
        for root in OUTPUT_ROOTS:
            candidate = root / safe_name
            if candidate.exists() and candidate.is_dir() and _is_relative_to(candidate, root):
                return candidate
        raise FileNotFoundError(f"training run not found: {safe_name}")

    runs = list_training_runs(limit=1)
    if not runs:
        raise FileNotFoundError("no training runs found under finetune/outputs")
    return Path(str(runs[0]["path"]))


def load_training_status(run_name: Optional[str] = None) -> Dict[str, Any]:
    run_dir = resolve_run_dir(run_name)
    artifacts = _run_artifacts(run_dir)
    stages: List[Dict[str, Any]] = []
    stage_names_with_progress = set()
    for progress_file in artifacts["progress"]:
        payload = _load_json(progress_file)
        stage = _summarize_stage(payload, progress_file)
        stages.append(stage)
        if stage.get("train_stage"):
            stage_names_with_progress.add(str(stage["train_stage"]))

    for manifest_file in artifacts["manifest"]:
        payload = _load_json(manifest_file)
        stage_name = str(payload.get("train_stage") or "")
        if stage_name and stage_name in stage_names_with_progress:
            continue
        stages.append(_manifest_as_stage(payload, manifest_file))

    stages.sort(key=lambda stage: (stage.get("stage_index") is None, stage.get("stage_index") or 99, stage.get("train_stage") or ""))
    statuses = {str(stage.get("status")) for stage in stages}
    if "running" in statuses:
        status = "running"
    elif "failed" in statuses:
        status = "failed"
    elif statuses and statuses <= {"ok", "dry_run", "recovered"}:
        status = "ok" if "ok" in statuses or "recovered" in statuses else "dry_run"
    elif statuses:
        status = sorted(statuses)[0]
    else:
        status = "unknown"
    percents = [stage.get("overall_percent") for stage in stages if isinstance(stage.get("overall_percent"), (int, float))]
    overall_percent = max(percents) if percents else 0.0
    latest_stage = max(stages, key=lambda stage: stage.get("updated_at") or "") if stages else None
    return {
        "run_name": run_dir.name,
        "run_path": str(run_dir),
        "status": status,
        "overall_percent": overall_percent,
        "stage_count": len(stages),
        "stages": stages,
        "latest_stage": latest_stage,
        "dataset_summary": load_dataset_summary(run_dir, artifacts),
        "updated_at": (latest_stage or {}).get("updated_at"),
        "generated_at": _utc_now(),
    }


def _artifact_record(path: Path, run_dir: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "name": path.name,
        "bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _safe_files_under(root: Path, run_dir: Path) -> List[Path]:
    if not root.exists() or not _is_relative_to(root, run_dir):
        return []
    return sorted((path for path in root.rglob("*") if path.is_file() and _is_relative_to(path, run_dir)), key=_file_mtime, reverse=True)


def _stage_artifact_status(run_dir: Path, stage_name: str, folder_name: str) -> Dict[str, Any]:
    logs_dir = run_dir / "logs"
    stage_dir = run_dir / folder_name
    checkpoint_dir = stage_dir / "checkpoints"
    checkpoint_files = _safe_files_under(checkpoint_dir, run_dir)
    best_model = checkpoint_dir / "best_model"
    progress_path = logs_dir / f"{stage_name}.progress.json"
    stdout_path = logs_dir / f"{stage_name}.stdout.log"
    stderr_path = logs_dir / f"{stage_name}.stderr.log"

    manifests: List[Path] = []
    for manifest_path in run_dir.glob("*run_manifest.json"):
        payload = _load_json(manifest_path)
        if str(payload.get("train_stage") or "") == stage_name:
            manifests.append(manifest_path)

    existing_support_files = [
        path for path in (progress_path, stdout_path, stderr_path, *manifests)
        if path.exists() and path.is_file() and _is_relative_to(path, run_dir)
    ]
    latest_candidates = checkpoint_files + existing_support_files
    latest_epoch = _latest_mtime(latest_candidates)

    return {
        "stage": stage_name,
        "folder": folder_name,
        "folder_exists": stage_dir.exists(),
        "checkpoint_dir": checkpoint_dir.resolve().relative_to(run_dir.resolve()).as_posix() if checkpoint_dir.exists() else None,
        "checkpoint_dir_exists": checkpoint_dir.exists(),
        "checkpoint_file_count": len(checkpoint_files),
        "checkpoint_ready": len(checkpoint_files) > 0,
        "best_model_exists": best_model.exists(),
        "progress_exists": progress_path.exists(),
        "stdout_exists": stdout_path.exists(),
        "stderr_exists": stderr_path.exists(),
        "manifest_count": len(manifests),
        "latest_updated_at": datetime.fromtimestamp(latest_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if latest_epoch else None,
        "recent_files": [_artifact_record(path, run_dir) for path in checkpoint_files[:10]],
    }


def inspect_training_artifacts(run_name: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Summarize checkpoint/model artifacts for a run without modifying outputs."""
    run_dir = resolve_run_dir(run_name)
    max_items = max(1, min(int(limit), 200))
    all_files = _safe_files_under(run_dir, run_dir)
    weight_files = [path for path in all_files if path.suffix.lower() in MODEL_WEIGHT_SUFFIXES]
    checkpoint_files = [
        path for path in all_files
        if path.suffix.lower() in MODEL_WEIGHT_SUFFIXES
        or "checkpoint" in path.name.lower()
        or any(part.lower() in {"checkpoints", "best_model"} for part in path.parts)
    ]

    tokenizer = _stage_artifact_status(run_dir, "tokenizer", "finetune_tokenizer")
    predictor = _stage_artifact_status(run_dir, "predictor", "finetune_predictor")
    predictor_started = bool(
        predictor["progress_exists"]
        or predictor["checkpoint_file_count"]
        or predictor["stdout_exists"]
    )
    predictor_ready = bool(predictor["checkpoint_ready"])
    tokenizer_ready = bool(tokenizer["checkpoint_ready"])
    any_checkpoint_ready = tokenizer_ready or predictor_ready or bool(checkpoint_files)
    latest_epoch = _latest_mtime(weight_files + checkpoint_files)

    if predictor_ready:
        level = "ready"
        label = "predictor checkpoint 준비"
        message = "predictor checkpoint가 확인되어 예측 산출물 생성/성과 검증 단계로 넘어갈 수 있습니다."
    elif predictor_started:
        level = "training"
        label = "predictor artifact 생성 중"
        message = "predictor 관련 로그나 progress는 보이지만 checkpoint 파일은 아직 확인되지 않았습니다."
    elif tokenizer_ready:
        level = "training"
        label = "tokenizer checkpoint 준비"
        message = "tokenizer checkpoint는 확인됐지만 predictor checkpoint는 아직 없습니다."
    else:
        level = "waiting"
        label = "checkpoint 대기"
        message = "현재 run에서 tokenizer/predictor checkpoint 또는 model weight 파일이 아직 확인되지 않았습니다."

    return {
        "run_name": run_dir.name,
        "run_path": str(run_dir),
        "generated_at": _utc_now(),
        "level": level,
        "label": label,
        "message": message,
        "checkpoint_ready": any_checkpoint_ready,
        "tokenizer_checkpoint_ready": tokenizer_ready,
        "predictor_started": predictor_started,
        "predictor_checkpoint_ready": predictor_ready,
        "model_weight_file_count": len(weight_files),
        "checkpoint_file_count": len(checkpoint_files),
        "latest_artifact_updated_at": datetime.fromtimestamp(latest_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if latest_epoch else None,
        "stages": {
            "tokenizer": tokenizer,
            "predictor": predictor,
        },
        "recent_model_weight_files": [_artifact_record(path, run_dir) for path in weight_files[:max_items]],
        "recent_checkpoint_files": [_artifact_record(path, run_dir) for path in checkpoint_files[:max_items]],
    }


def _tail_lines(path: Path, line_count: int) -> List[str]:
    tail: deque[str] = deque(maxlen=max(1, min(line_count, MAX_LOG_LINES)))
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            tail.append(line.rstrip("\r\n"))
    return list(tail)


def _select_training_stage(status: Dict[str, Any], stage: Optional[str]) -> Optional[Dict[str, Any]]:
    stages: Sequence[Dict[str, Any]] = status.get("stages", [])
    if stage:
        selected = next((item for item in stages if item.get("train_stage") == stage), None)
        if selected is not None:
            return selected
    latest = status.get("latest_stage")
    return latest if isinstance(latest, dict) else None


def _stage_stdout_log(
    run_dir: Path,
    selected_stage: Optional[Dict[str, Any]],
    allow_latest_fallback: bool = True,
) -> Optional[Path]:
    if selected_stage and selected_stage.get("stdout_log"):
        candidate = Path(str(selected_stage["stdout_log"]))
        if candidate.exists() and _is_relative_to(candidate, run_dir):
            return candidate
    if not allow_latest_fallback:
        return None
    logs = sorted((run_dir / "logs").glob("*.stdout.log"), key=_file_mtime, reverse=True)
    return logs[0] if logs else None


def _parse_train_step_line(line: str, selected_stage: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    match = TRAIN_STEP_RE.search(line)
    if not match:
        return None
    total_steps = int(match.group("total_steps"))
    step = int(match.group("step"))
    stage_percent = round(step / total_steps * 100.0, 4) if total_steps else 0.0
    stage_index = (selected_stage or {}).get("stage_index")
    stage_count = (selected_stage or {}).get("stage_count")
    overall_percent = stage_percent
    if isinstance(stage_index, int) and isinstance(stage_count, int) and stage_count > 0:
        overall_percent = round(((stage_index - 1) + stage_percent / 100.0) / stage_count * 100.0, 4)
    return {
        "rank": int(match.group("rank")),
        "epoch": int(match.group("epoch")),
        "epochs": int(match.group("epochs")),
        "step": step,
        "total_steps": total_steps,
        "stage_percent": stage_percent,
        "overall_percent": overall_percent,
        "learning_rate": float(match.group("learning_rate")),
        "loss": float(match.group("loss")),
        "line": line,
    }


def load_training_history(run_name: Optional[str] = None, stage: Optional[str] = None, limit: int = 40) -> Dict[str, Any]:
    """Return recent parsed train-step history from stdout logs without modifying files."""
    run_dir = resolve_run_dir(run_name)
    max_points = max(1, min(int(limit), 200))
    status = load_training_status(run_dir.name)
    selected_stage = _select_training_stage(status, stage)
    log_path = _stage_stdout_log(run_dir, selected_stage, allow_latest_fallback=stage is None)
    if log_path is None or not log_path.exists() or not _is_relative_to(log_path, run_dir):
        return {
            "run_name": run_dir.name,
            "stage": (selected_stage or {}).get("train_stage") or stage,
            "source_log_path": None,
            "points": [],
            "point_count": 0,
            "error": "no stdout log found for this run",
            "generated_at": _utc_now(),
        }

    parsed_points: List[Dict[str, Any]] = []
    for line in _tail_lines(log_path, max(max_points * 20, max_points)):
        point = _parse_train_step_line(line, selected_stage)
        if point:
            parsed_points.append(point)
    points = parsed_points[-max_points:]
    latest_progress = {
        "step": (selected_stage or {}).get("step"),
        "total_steps": (selected_stage or {}).get("total_steps"),
        "stage_percent": (selected_stage or {}).get("stage_percent"),
        "overall_percent": (selected_stage or {}).get("overall_percent"),
        "last_loss": (selected_stage or {}).get("last_loss"),
        "samples_per_second": (selected_stage or {}).get("samples_per_second"),
        "eta_seconds": (selected_stage or {}).get("eta_seconds"),
        "updated_at": (selected_stage or {}).get("updated_at"),
    }
    return {
        "run_name": run_dir.name,
        "stage": (selected_stage or {}).get("train_stage") or stage,
        "source_log_path": str(log_path),
        "points": points,
        "point_count": len(points),
        "latest_point": points[-1] if points else None,
        "latest_progress": latest_progress,
        "generated_at": _utc_now(),
    }


def tail_training_log(run_name: Optional[str] = None, stage: Optional[str] = None, lines: int = 200) -> Dict[str, Any]:
    run_dir = resolve_run_dir(run_name)
    line_count = max(1, min(int(lines), MAX_LOG_LINES))
    status = load_training_status(run_dir.name)
    selected_stage = _select_training_stage(status, stage)
    log_path = _stage_stdout_log(run_dir, selected_stage)
    if log_path is None or not log_path.exists() or not _is_relative_to(log_path, run_dir):
        return {
            "run_name": run_dir.name,
            "stage": stage,
            "log_path": None,
            "lines": [],
            "text": "",
            "error": "no stdout log found for this run",
        }
    lines_payload = _tail_lines(log_path, line_count)
    return {
        "run_name": run_dir.name,
        "stage": (selected_stage or {}).get("train_stage") or stage,
        "log_path": str(log_path),
        "lines": lines_payload,
        "text": "\n".join(lines_payload),
    }


def _number_or_none(value: str) -> Optional[float]:
    value = value.strip()
    if not value or value.upper() in {"N/A", "[NOT SUPPORTED]", "NOT SUPPORTED"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _round_or_none(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not (numeric == numeric):  # NaN guard without importing math.
        return None
    return round(numeric, digits)


def _run_powershell_float(script: str, timeout_seconds: int = 3) -> Optional[float]:
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        value = _number_or_none(line)
        if value is not None:
            return value
    return None


def _query_windows_cpu_percent(timeout_seconds: int = 3) -> Optional[float]:
    if os.name != "nt":
        return None
    return _run_powershell_float(
        "(Get-CimInstance Win32_Processor | "
        "Measure-Object -Property LoadPercentage -Average).Average",
        timeout_seconds=timeout_seconds,
    )


def _query_windows_memory_percent(timeout_seconds: int = 3) -> Dict[str, Optional[float]]:
    if os.name != "nt":
        return {"used_percent": None, "total_bytes": None, "available_bytes": None}
    script = (
        "$os=Get-CimInstance Win32_OperatingSystem; "
        "$total=[double]$os.TotalVisibleMemorySize*1024; "
        "$free=[double]$os.FreePhysicalMemory*1024; "
        "if ($total -gt 0) { "
        "Write-Output ((($total-$free)/$total)*100); "
        "Write-Output $total; "
        "Write-Output $free }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        return {"used_percent": None, "total_bytes": None, "available_bytes": None}
    if completed.returncode != 0:
        return {"used_percent": None, "total_bytes": None, "available_bytes": None}
    values = [_number_or_none(line) for line in completed.stdout.splitlines()]
    values = [value for value in values if value is not None]
    return {
        "used_percent": _round_or_none(values[0] if len(values) > 0 else None),
        "total_bytes": _round_or_none(values[1] if len(values) > 1 else None, 0),
        "available_bytes": _round_or_none(values[2] if len(values) > 2 else None, 0),
    }


def _query_windows_cpu_temperature(timeout_seconds: int = 3) -> tuple[Optional[float], Optional[str]]:
    """Best-effort Windows ACPI thermal-zone temperature.

    Many desktop boards do not expose the CPU package sensor through this WMI
    class. When unavailable, the dashboard should show "미측정" instead of
    implying that CPU temperature is safe.
    """
    if os.name != "nt":
        return None, None
    raw = _run_powershell_float(
        "Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature "
        "-ErrorAction Stop | Select-Object -First 1 -ExpandProperty CurrentTemperature",
        timeout_seconds=timeout_seconds,
    )
    if raw is None:
        return None, None
    temp_c = raw / 10.0 - 273.15 if raw > 1000 else raw
    if temp_c < -20 or temp_c > 150:
        return None, None
    return round(temp_c, 1), "windows_acpi_thermal_zone"


def _query_psutil_temperature() -> tuple[Optional[float], Optional[str]]:
    if _psutil is None or not hasattr(_psutil, "sensors_temperatures"):
        return None, None
    try:
        sensors = _psutil.sensors_temperatures(fahrenheit=False)  # type: ignore[attr-defined]
    except Exception:
        return None, None
    candidates: List[tuple[str, float]] = []
    for sensor_name, entries in (sensors or {}).items():
        for entry in entries or []:
            current = getattr(entry, "current", None)
            if current is None:
                continue
            label = getattr(entry, "label", "") or sensor_name
            candidates.append((f"psutil:{sensor_name}:{label}", float(current)))
    if not candidates:
        return None, None
    source, value = max(candidates, key=lambda item: item[1])
    return round(value, 1), source


def query_system_status(timeout_seconds: int = 3, cache_seconds: int = 10) -> Dict[str, Any]:
    """Return best-effort CPU/memory telemetry for the local training host."""
    now = time.monotonic()
    cached = _SYSTEM_STATUS_CACHE.get("payload")
    if cached is not None and now < float(_SYSTEM_STATUS_CACHE.get("expires_at", 0.0)) and cache_seconds > 0:
        return dict(cached)

    cpu_source = None
    if _psutil is not None:
        try:
            cpu_percent = float(_psutil.cpu_percent(interval=0.1))
            cpu_source = "psutil"
        except Exception:
            cpu_percent = None
    else:
        cpu_percent = None

    if cpu_percent is None:
        cpu_percent = _query_windows_cpu_percent(timeout_seconds=timeout_seconds)
        cpu_source = "windows_cim" if cpu_percent is not None else None

    temp_c, temp_source = _query_psutil_temperature()
    if temp_c is None:
        temp_c, temp_source = _query_windows_cpu_temperature(timeout_seconds=timeout_seconds)

    if _psutil is not None:
        try:
            vm = _psutil.virtual_memory()
            memory = {
                "used_percent": _round_or_none(getattr(vm, "percent", None)),
                "total_bytes": _round_or_none(getattr(vm, "total", None), 0),
                "available_bytes": _round_or_none(getattr(vm, "available", None), 0),
            }
        except Exception:
            memory = {"used_percent": None, "total_bytes": None, "available_bytes": None}
    else:
        memory = _query_windows_memory_percent(timeout_seconds=timeout_seconds)

    temperature_percent = (
        round(max(0.0, min(100.0, float(temp_c) / CPU_TEMPERATURE_LIMIT_C * 100.0)), 2)
        if temp_c is not None
        else None
    )
    payload = {
        "available": cpu_percent is not None or temp_c is not None or memory.get("used_percent") is not None,
        "cpu": {
            "utilization_percent": _round_or_none(cpu_percent),
            "temperature_c": temp_c,
            "temperature_limit_c": CPU_TEMPERATURE_LIMIT_C,
            "temperature_percent": temperature_percent,
            "temperature_available": temp_c is not None,
            "temperature_source": temp_source,
            "utilization_source": cpu_source,
        },
        "memory": memory,
        "generated_at": _utc_now(),
    }
    _SYSTEM_STATUS_CACHE["payload"] = payload
    _SYSTEM_STATUS_CACHE["expires_at"] = now + max(0, cache_seconds)
    return dict(payload)


def query_gpu_status(timeout_seconds: int = 5) -> Dict[str, Any]:
    """Return current NVIDIA GPU utilization/power when nvidia-smi is available."""
    fields = [
        "index",
        "name",
        "utilization.gpu",
        "memory.used",
        "memory.total",
        "power.draw",
        "power.limit",
        "temperature.gpu",
    ]
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc), "gpus": [], "generated_at": _utc_now()}

    if completed.returncode != 0:
        return {
            "available": False,
            "error": completed.stderr.strip() or completed.stdout.strip(),
            "gpus": [],
            "generated_at": _utc_now(),
        }

    gpus: List[Dict[str, Any]] = []
    for row in completed.stdout.splitlines():
        parts = [part.strip() for part in row.split(",")]
        if len(parts) < len(fields):
            continue
        gpu = {
            "index": int(_number_or_none(parts[0]) or 0),
            "name": parts[1],
            "utilization_gpu_percent": _number_or_none(parts[2]),
            "memory_used_mib": _number_or_none(parts[3]),
            "memory_total_mib": _number_or_none(parts[4]),
            "power_draw_watts": _number_or_none(parts[5]),
            "power_limit_watts": _number_or_none(parts[6]),
            "temperature_c": _number_or_none(parts[7]),
        }
        if gpu["memory_used_mib"] is not None and gpu["memory_total_mib"]:
            gpu["memory_used_percent"] = round(gpu["memory_used_mib"] / gpu["memory_total_mib"] * 100.0, 2)
        else:
            gpu["memory_used_percent"] = None
        gpu["power_draw_available"] = gpu["power_draw_watts"] is not None
        gpus.append(gpu)

    power_values = [gpu["power_draw_watts"] for gpu in gpus if gpu["power_draw_watts"] is not None]
    total_power = sum(power_values) if power_values else None
    power_limit_values = [gpu["power_limit_watts"] for gpu in gpus if gpu["power_limit_watts"] is not None]
    total_power_limit = sum(power_limit_values) if power_limit_values else None
    utilization_values = [
        gpu["utilization_gpu_percent"] for gpu in gpus if gpu["utilization_gpu_percent"] is not None
    ]
    total_memory_used = sum(gpu["memory_used_mib"] or 0 for gpu in gpus)
    total_memory_capacity = sum(gpu["memory_total_mib"] or 0 for gpu in gpus)
    return {
        "available": bool(gpus),
        "gpus": gpus,
        "total_power_draw_watts": total_power,
        "total_power_limit_watts": total_power_limit,
        "power_draw_available": total_power is not None,
        "average_utilization_gpu_percent": round(sum(utilization_values) / len(utilization_values), 2)
        if utilization_values
        else None,
        "total_memory_used_mib": total_memory_used if total_memory_capacity else None,
        "total_memory_total_mib": total_memory_capacity if total_memory_capacity else None,
        "total_memory_used_percent": round(total_memory_used / total_memory_capacity * 100.0, 2)
        if total_memory_capacity
        else None,
        "generated_at": _utc_now(),
    }
