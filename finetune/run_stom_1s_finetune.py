"""Launch reproducible STOM 1-second Kronos QlibDataset fine-tuning runs."""

from __future__ import annotations

import argparse
from collections import deque
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_ROOT = PROJECT_ROOT / "finetune" / "qlib_exports"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "finetune" / "outputs"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_PREDICTOR = "NeoQuasar/Kronos-small"
try:
    from .training_progress import TrainingProgressTracker, build_dry_run_progress
except ImportError:  # pragma: no cover - direct script execution path
    from training_progress import TrainingProgressTracker, build_dry_run_progress

STOM_1S_FULL_SAMPLE_POOLS = {
    30: {"train": 75_277_195, "val": 16_275_307},
    60: {"train": 73_718_875, "val": 15_938_107},
}
SAMPLE_STAGE_PRESETS = {
    "budget_20k": {"train": 20_000, "val": 4_000},
    "expand_200k": {"train": 200_000, "val": 40_000},
    "expand_1m": {"train": 1_000_000, "val": 100_000},
    "expand_5m": {"train": 5_000_000, "val": 250_000},
    "full_window": None,
}
TRAIN_STAGES = {"tokenizer", "predictor", "both"}
RESUME_STAGES = {"tokenizer", "predictor"}
TOKENIZER_CHECKPOINT_POLICIES = {"best_then_latest", "best", "latest_train_model"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mode_default(value: Optional[int], mode: str, smoke: int, stage: int, full: int) -> int:
    if value is not None:
        return value
    if mode == "smoke":
        return smoke
    if mode == "stage":
        return stage
    return full


def _stage_override(
    base_value: Optional[int],
    tokenizer_value: Optional[int],
    predictor_value: Optional[int],
    train_stage: str,
) -> Optional[int]:
    """Resolve a per-stage CLI override while preserving the existing shared default."""

    if train_stage == "tokenizer" and tokenizer_value is not None:
        return tokenizer_value
    if train_stage == "predictor" and predictor_value is not None:
        return predictor_value
    return base_value


def _tail(text: str, limit: int = 8000) -> str:
    return text[-limit:] if len(text) > limit else text


def sample_stage_budget(stage: Optional[str], horizon: int) -> Optional[Dict[str, int]]:
    if not stage:
        return None
    if stage == "full_window":
        return dict(STOM_1S_FULL_SAMPLE_POOLS[horizon])
    preset = SAMPLE_STAGE_PRESETS.get(stage)
    if preset is None:
        raise ValueError(f"Unknown sample stage: {stage}")
    return dict(preset)


def _checkpoint_has_model_weights(path: Path) -> bool:
    """Return True when a Hugging Face checkpoint folder has model weights."""

    if not path.is_dir():
        return False
    return any((path / name).exists() for name in ("model.safetensors", "pytorch_model.bin"))


def resolve_tokenizer_handoff_checkpoint(
    save_path: Path,
    tokenizer_save_folder: str,
    policy: str,
) -> tuple[Path, str]:
    """Pick the tokenizer checkpoint used by the predictor handoff.

    Full STOM runs save ``latest_train_model`` before tokenizer validation.
    Validation can be much slower than training when the validation batch size
    is forced to 1 for OOM safety, so the default policy keeps the official
    ``best_model`` path when it exists and safely falls back to the trained
    pre-validation checkpoint when it is the only available checkpoint.
    """

    checkpoint_root = save_path / tokenizer_save_folder / "checkpoints"
    best_model = checkpoint_root / "best_model"
    latest_train_model = checkpoint_root / "latest_train_model"
    if policy == "best":
        return best_model, "best_model"
    if policy == "latest_train_model":
        return latest_train_model, "latest_train_model"
    if policy != "best_then_latest":
        raise ValueError(f"Unknown tokenizer checkpoint policy: {policy}")
    if _checkpoint_has_model_weights(best_model):
        return best_model, "best_model"
    if _checkpoint_has_model_weights(latest_train_model):
        return latest_train_model, "latest_train_model"
    return best_model, "best_model_expected"


def build_run(
    horizon: int,
    args: argparse.Namespace,
    mode: str,
    train_stage: Optional[str] = None,
) -> Dict[str, Any]:
    dataset_dir = Path(args.dataset_dir) if args.dataset_dir else (
        DEFAULT_EXPORT_ROOT / f"stom_1s_grid_pred{horizon}_full" / "processed_datasets"
    )
    dataset_dir = dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"processed_datasets not found: {dataset_dir}")
    for required in ["train_data.pkl", "val_data.pkl"]:
        if not (dataset_dir / required).exists():
            raise FileNotFoundError(f"required dataset file missing: {dataset_dir / required}")

    sample_budget = sample_stage_budget(args.sample_stage, horizon)
    run_suffix = args.sample_stage or mode
    run_name = args.run_name or f"stom_1s_grid_pred{horizon}_{run_suffix}"
    save_path = (Path(args.output_root).resolve() if args.output_root else DEFAULT_OUTPUT_ROOT) / run_name
    log_dir = save_path / "logs"
    normalized_stage = train_stage or getattr(args, "train_stage", "predictor")
    if normalized_stage == "both":
        normalized_stage = "predictor"
    requested_train_stage = getattr(args, "train_stage", normalized_stage)
    stage_count = 2 if requested_train_stage == "both" else 1
    if stage_count == 2:
        stage_index = 1 if normalized_stage == "tokenizer" else 2
    else:
        stage_index = 1
    manifest_name = "run_manifest.json" if normalized_stage == "predictor" else f"{normalized_stage}_run_manifest.json"
    manifest_path = save_path / manifest_name

    epochs = _mode_default(args.epochs, mode, smoke=1, stage=1, full=1)
    batch_size_arg = _stage_override(
        args.batch_size,
        args.tokenizer_batch_size,
        args.predictor_batch_size,
        normalized_stage,
    )
    num_workers = _stage_override(
        args.num_workers,
        args.tokenizer_num_workers,
        args.predictor_num_workers,
        normalized_stage,
    )
    batch_size = _mode_default(batch_size_arg, mode, smoke=1, stage=4, full=4)
    tokenizer_val_batch_size = _mode_default(
        args.tokenizer_val_batch_size,
        mode,
        smoke=1,
        stage=2,
        full=1,
    )
    default_train = sample_budget["train"] if sample_budget else _mode_default(None, mode, smoke=2, stage=512, full=20_000)
    default_val = sample_budget["val"] if sample_budget else _mode_default(None, mode, smoke=2, stage=128, full=4_000)
    n_train_iter = args.n_train_iter if args.n_train_iter is not None else default_train
    n_val_iter = args.n_val_iter if args.n_val_iter is not None else default_val
    log_interval = _mode_default(args.log_interval, mode, smoke=1, stage=25, full=100)

    env = {
        "KRONOS_DATASET_PATH": str(dataset_dir),
        "KRONOS_LOOKBACK_WINDOW": str(args.lookback_window),
        "KRONOS_PREDICT_WINDOW": str(horizon),
        "KRONOS_EPOCHS": str(epochs),
        "KRONOS_BATCH_SIZE": str(batch_size),
        "KRONOS_N_TRAIN_ITER": str(n_train_iter),
        "KRONOS_N_VAL_ITER": str(n_val_iter),
        "KRONOS_LOG_INTERVAL": str(log_interval),
        "KRONOS_NUM_WORKERS": str(num_workers),
        "KRONOS_USE_COMET": "0",
        "KRONOS_SAVE_PATH": str(save_path),
        "KRONOS_TOKENIZER_SAVE_FOLDER": args.tokenizer_save_folder,
        "KRONOS_PREDICTOR_SAVE_FOLDER": args.predictor_save_folder,
        "KRONOS_PRETRAINED_TOKENIZER_PATH": args.pretrained_tokenizer_path,
        "KRONOS_PRETRAINED_PREDICTOR_PATH": args.pretrained_predictor_path,
        "KRONOS_DDP_BACKEND": args.ddp_backend,
        "KRONOS_DATASET_SAMPLE_MODE": args.dataset_sample_mode,
        "USE_LIBUV": "0",
        "PYTHONUNBUFFERED": "1",
    }
    if normalized_stage == "tokenizer":
        env["KRONOS_TOKENIZER_VAL_BATCH_SIZE"] = str(tokenizer_val_batch_size)
        env["KRONOS_TOKENIZER_SAVE_PRE_VAL_CHECKPOINT"] = "1"
        env["KRONOS_TOKENIZER_EMPTY_CACHE_BEFORE_VAL"] = "1"
        # ── GPU 최대 활용 최적화 (opt-in flags propagation) ──────
        if getattr(args, "persistent_workers", False):
            env["KRONOS_PERSISTENT_WORKERS"] = "1"
        prefetch_factor_val = getattr(args, "prefetch_factor", None)
        if prefetch_factor_val is not None:
            env["KRONOS_PREFETCH_FACTOR"] = str(prefetch_factor_val)
        if getattr(args, "tokenizer_amp", False):
            env["KRONOS_TOKENIZER_AMP"] = "1"
            env["KRONOS_TOKENIZER_AMP_DTYPE"] = str(getattr(args, "tokenizer_amp_dtype", "bf16"))
        if getattr(args, "tokenizer_compile", False):
            env["KRONOS_TOKENIZER_COMPILE"] = "1"
            env["KRONOS_TOKENIZER_COMPILE_MODE"] = str(getattr(args, "tokenizer_compile_mode", "reduce-overhead"))
            if getattr(args, "tokenizer_compile_fullgraph", False):
                env["KRONOS_TOKENIZER_COMPILE_FULLGRAPH"] = "1"
    if args.nproc_per_node == 1:
        env.update(
            {
                "RANK": "0",
                "WORLD_SIZE": "1",
                "LOCAL_RANK": "0",
                "MASTER_ADDR": args.master_addr,
                "MASTER_PORT": str(args.master_port),
                "KRONOS_DISABLE_DDP": "1",
            }
        )
    tokenizer_handoff_checkpoint: Optional[Path] = None
    tokenizer_handoff_source: Optional[str] = None
    if args.finetuned_tokenizer_path:
        tokenizer_handoff_checkpoint = Path(args.finetuned_tokenizer_path).resolve()
        tokenizer_handoff_source = "explicit"
        env["KRONOS_FINETUNED_TOKENIZER_PATH"] = str(tokenizer_handoff_checkpoint)
    elif normalized_stage == "predictor" and getattr(args, "train_stage", "predictor") == "both":
        tokenizer_handoff_checkpoint, tokenizer_handoff_source = resolve_tokenizer_handoff_checkpoint(
            save_path,
            args.tokenizer_save_folder,
            getattr(args, "tokenizer_checkpoint_policy", "best_then_latest"),
        )
        env["KRONOS_FINETUNED_TOKENIZER_PATH"] = str(tokenizer_handoff_checkpoint)
    if args.finetuned_predictor_path:
        env["KRONOS_FINETUNED_PREDICTOR_PATH"] = str(Path(args.finetuned_predictor_path).resolve())

    if args.nproc_per_node == 1:
        script_name = "train_tokenizer.py" if normalized_stage == "tokenizer" else "train_predictor.py"
        command = [sys.executable, str(PROJECT_ROOT / "finetune" / script_name)]
    else:
        script_name = "train_tokenizer.py" if normalized_stage == "tokenizer" else "train_predictor.py"
        command = [
            sys.executable,
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc_per_node",
            str(args.nproc_per_node),
            str(PROJECT_ROOT / "finetune" / script_name),
        ]

    return {
        "horizon": horizon,
        "mode": mode,
        "train_stage": normalized_stage,
        "requested_train_stage": requested_train_stage,
        "stage_index": stage_index,
        "stage_count": stage_count,
        "sample_stage": args.sample_stage,
        "target_train_samples": n_train_iter,
        "target_val_samples": n_val_iter,
        "known_full_sample_pool": STOM_1S_FULL_SAMPLE_POOLS.get(horizon),
        "run_name": run_name,
        "dataset_dir": str(dataset_dir),
        "save_path": str(save_path),
        "log_dir": str(log_dir),
        "manifest_path": str(manifest_path),
        "command": command,
        "env": env,
        "tokenizer_checkpoint_policy": getattr(args, "tokenizer_checkpoint_policy", "best_then_latest"),
        "tokenizer_handoff_checkpoint": str(tokenizer_handoff_checkpoint) if tokenizer_handoff_checkpoint else None,
        "tokenizer_handoff_source": tokenizer_handoff_source,
    }


def execute_run(spec: Mapping[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    save_path = Path(str(spec["save_path"]))
    log_dir = Path(str(spec["log_dir"]))
    manifest_path = Path(str(spec["manifest_path"]))
    log_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    stage_name = str(spec.get("train_stage", "train"))
    stdout_path = log_dir / f"{stage_name}.stdout.log"
    stderr_path = log_dir / f"{stage_name}.stderr.log"
    progress_path = log_dir / f"{stage_name}.progress.json"

    payload: Dict[str, Any] = {
        "created_at": _utc_now(),
        "status": "dry_run" if dry_run else "running",
        **{k: v for k, v in spec.items() if k not in {"env"}},
        "env_overrides": dict(spec["env"]),
        "progress_path": str(progress_path),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if dry_run:
        stdout_path.write_text(
            f"dry-run only; {spec.get('train_stage', 'training')} command was not executed.\n",
            encoding="utf-8",
        )
        stderr_path.write_text("dry-run only; no stderr was produced.\n", encoding="utf-8")
        build_dry_run_progress(spec, progress_path, stdout_path, stderr_path, manifest_path)
        return payload

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in spec["env"].items()})
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    started = datetime.now(timezone.utc)
    tracker = TrainingProgressTracker(
        spec=spec,
        progress_path=progress_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        manifest_path=manifest_path,
    )
    stdout_tail: deque[str] = deque(maxlen=400)
    stderr_note = "stderr is merged into stdout so the live dashboard can stream one ordered log.\n"
    stderr_path.write_text(stderr_note, encoding="utf-8")

    try:
        process = subprocess.Popen(
            list(spec["command"]),
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception as exc:
        tracker.fail_before_start(str(exc))
        payload.update(
            {
                "completed_at": _utc_now(),
                "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
                "returncode": -1,
                "status": "failed",
                "stdout_tail": "",
                "stderr_tail": str(exc),
            }
        )
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise

    tracker.start(process.pid)
    with stdout_path.open("w", encoding="utf-8", buffering=1) as stdout_file:
        if process.stdout is not None:
            for line in process.stdout:
                stdout_file.write(line)
                stdout_file.flush()
                stdout_tail.append(line)
                tracker.observe_line(line)
                print(line, end="", flush=True)
    returncode = process.wait()
    tracker.finish(returncode)

    payload.update(
        {
            "completed_at": _utc_now(),
            "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
            "returncode": returncode,
            "status": "ok" if returncode == 0 else "failed",
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "progress_path": str(progress_path),
            "stdout_tail": _tail("".join(stdout_tail)),
            "stderr_tail": stderr_note,
        }
    )
    summary_folder_key = (
        "KRONOS_TOKENIZER_SAVE_FOLDER" if spec.get("train_stage") == "tokenizer" else "KRONOS_PREDICTOR_SAVE_FOLDER"
    )
    summary_path = save_path / str(spec["env"][summary_folder_key]) / "summary.json"
    if summary_path.exists():
        payload["summary_path"] = str(summary_path)
        payload["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if returncode != 0:
        raise RuntimeError(
            f"{spec.get('train_stage', 'predictor')} fine-tuning failed for pred{spec['horizon']}; see {stdout_path}"
        )
    return payload


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run STOM 1-second Kronos fine-tuning from QlibDataset pickles.")
    parser.add_argument("--horizon", choices=["30", "60", "all"], default="all")
    parser.add_argument("--mode", choices=["smoke", "stage", "full"], default="stage")
    parser.add_argument(
        "--train-stage",
        choices=sorted(TRAIN_STAGES),
        default="predictor",
        help="Run tokenizer, predictor, or tokenizer then predictor. Official Kronos fine-tuning uses both.",
    )
    parser.add_argument(
        "--start-stage",
        choices=sorted(RESUME_STAGES),
        default=None,
        help="Resume a --train-stage both run from tokenizer or predictor while preserving 2-stage progress.",
    )
    parser.add_argument(
        "--sample-stage",
        choices=sorted(SAMPLE_STAGE_PRESETS),
        default=None,
        help=(
            "Optional staged full-data training budget. "
            "Use budget_20k -> expand_200k -> expand_1m -> expand_5m -> full_window."
        ),
    )
    parser.add_argument("--dataset-dir", default=None, help="Override processed_datasets directory; only valid for one horizon.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", default=None, help="Override run name; only valid for one horizon.")
    parser.add_argument("--lookback-window", type=int, default=300)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument(
        "--tokenizer-batch-size",
        type=int,
        default=None,
        help="Tokenizer-only batch-size override for --train-stage both handoff runs.",
    )
    parser.add_argument(
        "--tokenizer-val-batch-size",
        type=int,
        default=None,
        help=(
            "Tokenizer validation-only batch-size override. "
            "Defaults to 1 in full mode to avoid post-training CUDA OOM."
        ),
    )
    parser.add_argument(
        "--tokenizer-checkpoint-policy",
        choices=sorted(TOKENIZER_CHECKPOINT_POLICIES),
        default="best_then_latest",
        help=(
            "Predictor handoff policy for --train-stage both. "
            "best_then_latest uses best_model when present and latest_train_model when validation has not finished."
        ),
    )
    parser.add_argument(
        "--predictor-batch-size",
        type=int,
        default=None,
        help="Predictor-only batch-size override for --train-stage both handoff runs.",
    )
    # ── GPU 최대 활용 최적화 옵션 (opt-in, default 는 기존 동작 유지) ──
    parser.add_argument(
        "--persistent-workers",
        action="store_true",
        help="DataLoader persistent_workers=True (num_workers > 0 일 때만 효과).",
    )
    parser.add_argument(
        "--prefetch-factor",
        type=int,
        default=None,
        help="DataLoader prefetch_factor (default 2). num_workers > 0 일 때만 효과.",
    )
    parser.add_argument(
        "--tokenizer-amp",
        action="store_true",
        help="Tokenizer 학습 시 mixed precision (autocast) 사용. dtype 은 --tokenizer-amp-dtype.",
    )
    parser.add_argument(
        "--tokenizer-amp-dtype",
        choices=["bf16", "fp16", "fp32"],
        default="bf16",
        help="AMP dtype. bf16 권장 (4080 SUPER 가속 + GradScaler 불필요).",
    )
    parser.add_argument(
        "--tokenizer-compile",
        action="store_true",
        help="Tokenizer 모델을 torch.compile 로 래핑. 첫 epoch 컴파일 오버헤드 발생.",
    )
    parser.add_argument(
        "--tokenizer-compile-mode",
        choices=["default", "reduce-overhead", "max-autotune"],
        default="reduce-overhead",
        help="torch.compile mode. reduce-overhead 가 일반 학습에 적합.",
    )
    parser.add_argument(
        "--tokenizer-compile-fullgraph",
        action="store_true",
        help="torch.compile fullgraph=True. Kronos rotary attention 호환 실패 시 비활성화 필요.",
    )
    parser.add_argument("--n-train-iter", type=int, default=None)
    parser.add_argument("--n-val-iter", type=int, default=None)
    parser.add_argument("--log-interval", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument(
        "--tokenizer-num-workers",
        type=int,
        default=None,
        help="Tokenizer-only DataLoader worker override for --train-stage both handoff runs.",
    )
    parser.add_argument(
        "--predictor-num-workers",
        type=int,
        default=None,
        help="Predictor-only DataLoader worker override for --train-stage both handoff runs.",
    )
    parser.add_argument(
        "--dataset-sample-mode",
        choices=["sample_random", "full_sequential"],
        default="sample_random",
        help="sample_random keeps the original Kronos demo behavior; full_sequential makes dataset idx authoritative.",
    )
    parser.add_argument("--nproc-per-node", type=int, default=1)
    parser.add_argument("--ddp-backend", default="gloo")
    parser.add_argument("--master-addr", default="127.0.0.1")
    parser.add_argument("--master-port", type=int, default=29531)
    parser.add_argument("--pretrained-tokenizer-path", default=DEFAULT_TOKENIZER)
    parser.add_argument("--pretrained-predictor-path", default=DEFAULT_PREDICTOR)
    parser.add_argument("--finetuned-tokenizer-path", default=None)
    parser.add_argument("--finetuned-predictor-path", default=None)
    parser.add_argument("--tokenizer-save-folder", default="finetune_tokenizer")
    parser.add_argument("--predictor-save-folder", default="finetune_predictor")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.dataset_dir and args.horizon == "all":
        raise ValueError("--dataset-dir can only be used with --horizon 30 or --horizon 60")
    if args.run_name and args.horizon == "all":
        raise ValueError("--run-name can only be used with --horizon 30 or --horizon 60")
    if args.start_stage and args.train_stage != "both":
        raise ValueError("--start-stage is only valid with --train-stage both")

    horizons: List[int] = [30, 60] if args.horizon == "all" else [int(args.horizon)]
    results = []
    for horizon in horizons:
        stages = ["tokenizer", "predictor"] if args.train_stage == "both" else [args.train_stage]
        if args.start_stage:
            stages = stages[stages.index(args.start_stage):]
        for stage in stages:
            spec = build_run(horizon, args, args.mode, train_stage=stage)
            result = execute_run(spec, dry_run=args.dry_run)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
