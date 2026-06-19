"""Preflight checks before a 2025-only STOM 1s Kronos-small full run.

The script is read-only for the source SQLite database. It does not start
training and does not create large datasets; it verifies whether the machine and
repository are ready, then prints the exact export/training commands that should
be launched by the next long-running step.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_CSV_DIR = PROJECT_ROOT / "finetune_csv"
if str(FINETUNE_CSV_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_CSV_DIR))

from stom_tick_dataset import connect_readonly, list_stock_tables  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "_database" / "stock_tick_back.db"
DEFAULT_SCAN_REPORT = PROJECT_ROOT / ".omx" / "analysis" / "stom_2025_db_sample_time_report.json"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "finetune" / "qlib_exports" / "stom_1s_grid_pred60_2025"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "finetune" / "outputs"
DEFAULT_RUN_NAME = "stom_1s_grid_pred60_2025_full_small"
DEFAULT_TRAIN_SAMPLES = 18_771_531
DEFAULT_VAL_SAMPLES = 3_922_758
MEASURED_4080S_SECONDS_PER_240K = 7_340.567561


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _powershell_quote(value: Path | str) -> str:
    text = str(value)
    return f'"{text}"' if " " in text else text


def _disk_report(path: Path) -> Dict[str, Any]:
    target = path if path.exists() else path.parent
    usage = shutil.disk_usage(target)
    return {
        "path": str(path),
        "free_bytes": usage.free,
        "free_gb": round(usage.free / (1024**3), 2),
        "total_gb": round(usage.total / (1024**3), 2),
    }


def _cuda_report(python_exe: str) -> Dict[str, Any]:
    code = r"""
import json
import sys
payload = {"python": sys.executable}
try:
    import torch
    payload["torch_version"] = torch.__version__
    payload["cuda_available"] = bool(torch.cuda.is_available())
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        payload["gpu_name"] = torch.cuda.get_device_name(0)
        payload["capability"] = list(torch.cuda.get_device_capability(0))
        payload["memory_total_bytes"] = int(props.total_memory)
        payload["memory_total_gb"] = round(props.total_memory / (1024**3), 2)
except Exception as exc:
    payload["error"] = repr(exc)
print(json.dumps(payload, ensure_ascii=False))
"""
    completed = subprocess.run(
        [python_exe, "-c", code],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "python": python_exe,
            "error": completed.stderr.strip() or completed.stdout.strip(),
            "cuda_available": False,
        }
    return json.loads(completed.stdout)


def _db_report(db_path: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "size_gb": round(db_path.stat().st_size / (1024**3), 2) if db_path.exists() else 0,
    }
    if not db_path.exists():
        return payload
    conn = connect_readonly(db_path)
    try:
        payload["query_only"] = conn.execute("PRAGMA query_only").fetchone()[0]
        payload["table_count"] = len(list_stock_tables(conn, max_tables=None))
        try:
            conn.execute("CREATE TABLE __kronos_preflight_write_probe(x INTEGER)")
            payload["write_probe_blocked"] = False
        except sqlite3.DatabaseError as exc:
            payload["write_probe_blocked"] = True
            payload["write_probe_error"] = str(exc)
    finally:
        conn.close()
    return payload


def _artifact_exists(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
    }


def _sample_counts_from_scan(scan_report: Optional[Dict[str, Any]], train_default: int, val_default: int) -> tuple[int, int, str]:
    if scan_report is None:
        return train_default, val_default, "built_in_defaults"
    split = scan_report.get("split_by_session_70_15_15", {})
    train = int(split.get("train", {}).get("possible_samples_pred60", train_default))
    val = int(split.get("val", {}).get("possible_samples_pred60", val_default))
    return train, val, "scan_report"


def _sample_counts_from_export_report(
    export_report: Optional[Dict[str, Any]],
    lookback_window: int,
    horizon: int,
) -> Optional[tuple[int, int]]:
    if export_report is None:
        return None
    split_counts = export_report.get("split_counts", {})
    train = split_counts.get("train", {})
    val = split_counts.get("val", {})
    window_offset = lookback_window + horizon
    if not train or not val:
        return None
    train_samples = int(train.get("rows", 0)) - int(train.get("groups", 0)) * window_offset
    val_samples = int(val.get("rows", 0)) - int(val.get("groups", 0)) * window_offset
    if train_samples <= 0 or val_samples <= 0:
        return None
    return train_samples, val_samples


def build_preflight(args: argparse.Namespace) -> Dict[str, Any]:
    db_path = Path(args.db).resolve()
    export_dir = Path(args.export_dir).resolve()
    dataset_dir = export_dir / "processed_datasets"
    output_root = Path(args.output_root).resolve()
    run_dir = output_root / args.run_name
    scan_report_path = Path(args.scan_report).resolve()
    scan_report = _load_json(scan_report_path)
    export_report_path = export_dir / "stom_qlib_export_report.json"
    export_report = _load_json(export_report_path)

    train_default = int(args.train_samples or DEFAULT_TRAIN_SAMPLES)
    val_default = int(args.val_samples or DEFAULT_VAL_SAMPLES)
    train_samples, val_samples, sample_source = _sample_counts_from_scan(scan_report, train_default, val_default)
    export_samples = _sample_counts_from_export_report(export_report, args.lookback_window, args.horizon)
    if export_samples:
        train_samples, val_samples = export_samples
        sample_source = "export_report"
    total_samples = train_samples + val_samples
    estimated_seconds = MEASURED_4080S_SECONDS_PER_240K * (total_samples / 240_000)

    export_command = [
        args.python_exe,
        "finetune/qlib_stom_pipeline.py",
        "export",
        "--db",
        _rel(db_path),
        "--output-dir",
        _rel(export_dir),
        "--lookback-window",
        str(args.lookback_window),
        "--predict-window",
        str(args.horizon),
        "--horizon-seconds",
        str(args.horizon),
        "--price-mode",
        "close_only",
        "--time-start",
        args.time_start,
        "--time-end",
        args.time_end,
        "--session-start",
        f"{args.year}0101",
        "--session-end",
        f"{args.year}1231",
        "--freq",
        "1s",
        "--regularize-1s",
        "--split-by",
        "session",
    ]
    train_command = [
        args.python_exe,
        "finetune/run_stom_1s_finetune.py",
        "--horizon",
        str(args.horizon),
        "--mode",
        "full",
        "--train-stage",
        "both",
        "--dataset-dir",
        _rel(dataset_dir),
        "--run-name",
        args.run_name,
        "--dataset-sample-mode",
        "full_sequential",
        "--batch-size",
        str(args.batch_size),
        "--num-workers",
        str(args.num_workers),
        "--n-train-iter",
        str(train_samples),
        "--n-val-iter",
        str(val_samples),
        "--log-interval",
        str(args.log_interval),
    ]

    expected_paths = {
        "dataset_dir": str(dataset_dir),
        "train_pkl": _artifact_exists(dataset_dir / "train_data.pkl"),
        "val_pkl": _artifact_exists(dataset_dir / "val_data.pkl"),
        "test_pkl": _artifact_exists(dataset_dir / "test_data.pkl"),
        "run_dir": str(run_dir),
        "tokenizer_checkpoint": str(run_dir / "finetune_tokenizer" / "checkpoints" / "best_model"),
        "predictor_checkpoint": str(run_dir / "finetune_predictor" / "checkpoints" / "best_model"),
    }
    existing_200k = PROJECT_ROOT / "finetune" / "outputs" / "stom_1s_grid_pred60_official_200k"
    blockers = []
    warnings = []

    db = _db_report(db_path)
    if not db.get("exists"):
        blockers.append("STOM tick DB is missing.")
    if db.get("query_only") != 1:
        blockers.append("DB read-only/query_only check failed.")
    if db.get("write_probe_blocked") is False:
        blockers.append("DB write probe was not blocked.")

    cuda = _cuda_report(args.python_exe)
    if not cuda.get("cuda_available"):
        blockers.append("CUDA is not available.")
    elif cuda.get("memory_total_gb", 0) < 12:
        warnings.append("VRAM is below 12GB; Kronos-small full run batch_size=4 may be unstable.")

    if scan_report is None:
        warnings.append("2025 exact scan report is missing; built-in sample estimates were used.")

    if not (existing_200k / "finetune_tokenizer" / "checkpoints" / "best_model").exists():
        warnings.append("Official 200k tokenizer checkpoint was not found.")
    if not (existing_200k / "finetune_predictor" / "checkpoints" / "best_model").exists():
        warnings.append("Official 200k predictor checkpoint was not found.")

    if not (dataset_dir / "train_data.pkl").exists():
        warnings.append("2025 processed dataset does not exist yet; run the export command first.")

    output_disk = _disk_report(output_root)
    export_disk = _disk_report(export_dir)
    if export_disk["free_gb"] < 50:
        warnings.append("Export path has less than 50GB free space.")
    if output_disk["free_gb"] < 20:
        warnings.append("Output path has less than 20GB free space.")

    return {
        "created_at": _utc_now(),
        "status": "blocked" if blockers else "ready_with_actions",
        "year": args.year,
        "horizon": args.horizon,
        "lookback_window": args.lookback_window,
        "target_samples": {
            "train": train_samples,
            "val": val_samples,
            "train_plus_val": total_samples,
            "source": sample_source,
        },
        "estimated_4080s_runtime": {
            "seconds": round(estimated_seconds, 2),
            "hours": round(estimated_seconds / 3600, 2),
            "days": round(estimated_seconds / 86400, 2),
            "basis": "Measured official 200k tokenizer+predictor: 7,340.567561 seconds per 240k samples.",
        },
        "db": db,
        "cuda": cuda,
        "disk": {"export_root": export_disk, "output_root": output_disk},
        "scan_report_loaded": scan_report is not None,
        "scan_report_path": str(scan_report_path),
        "export_report_loaded": export_report is not None,
        "export_report_path": str(export_report_path),
        "expected_artifacts": expected_paths,
        "commands": {
            "export_2025_dataset": " ".join(_powershell_quote(part) for part in export_command),
            "train_2025_full_small": " ".join(_powershell_quote(part) for part in train_command),
            "dashboard_after_prediction": "python webui/run.py --host 127.0.0.1 --port 5000",
        },
        "warnings": warnings,
        "blockers": blockers,
        "next_action": (
            "run_training_2025_full_small"
            if not blockers and (dataset_dir / "train_data.pkl").exists() and (dataset_dir / "val_data.pkl").exists()
            else "run_export_2025_dataset"
            if not blockers
            else "resolve_blockers"
        ),
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--year", default="2025")
    parser.add_argument("--horizon", type=int, default=60)
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--time-start", default="090000")
    parser.add_argument("--time-end", default="093000")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", default=DEFAULT_RUN_NAME)
    parser.add_argument("--scan-report", default=str(DEFAULT_SCAN_REPORT))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--log-interval", type=int, default=1000)
    parser.add_argument("--train-samples", type=int, default=None)
    parser.add_argument("--val-samples", type=int, default=None)
    parser.add_argument("--json-output", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    report = build_preflight(args)
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
