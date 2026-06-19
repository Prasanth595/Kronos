import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

try:
    from config_loader import CustomFinetuneConfig
except Exception:  # pragma: no cover - config loader diagnostics are reported by env-check
    CustomFinetuneConfig = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "_database" / "stock_tick_back.db"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "finetune_csv" / "configs" / "config_stom_1tick.yaml"
DEFAULT_PILOT_CSV = PROJECT_ROOT / "finetune_csv" / "data" / "stom_1tick_kline_pilot.csv"


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _torch_status() -> Dict[str, Any]:
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        devices = []
        if cuda_available:
            for idx in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(idx)
                devices.append(
                    {
                        "index": idx,
                        "name": props.name,
                        "total_memory_gb": round(props.total_memory / (1024**3), 2),
                    }
                )
        return {
            "available": True,
            "version": getattr(torch, "__version__", "unknown"),
            "cuda_available": cuda_available,
            "cuda_version": getattr(torch.version, "cuda", None),
            "devices": devices,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def env_check(
    db_path: Path = DEFAULT_DB_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return JSON-serializable environment readiness for STOM OHLCV training."""

    db_path = Path(db_path)
    config_path = Path(config_path)
    dependencies = {
        "numpy": _module_available("numpy"),
        "pandas": _module_available("pandas"),
        "torch": _module_available("torch"),
        "huggingface_hub": _module_available("huggingface_hub"),
        "flask": _module_available("flask"),
        "plotly": _module_available("plotly"),
    }
    status = {
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
        },
        "paths": {
            "project_root": str(PROJECT_ROOT),
            "db_path": str(db_path),
            "db_exists": db_path.exists(),
            "db_size_bytes": db_path.stat().st_size if db_path.exists() else None,
            "config_path": str(config_path),
            "config_exists": config_path.exists(),
        },
        "dependencies": dependencies,
        "torch": _torch_status(),
        "recommendations": [],
    }

    if not status["torch"].get("cuda_available"):
        status["recommendations"].append(
            "CUDA is not available from the current Python. Install a CUDA-enabled PyTorch build before full GPU training."
        )
    if not dependencies.get("huggingface_hub"):
        status["recommendations"].append(
            "huggingface_hub is missing. Install requirements before loading Kronos pretrained models."
        )
    if not dependencies.get("flask") or not dependencies.get("plotly"):
        status["recommendations"].append(
            "webui dependencies are incomplete. Run: python -m pip install -r webui/requirements.txt"
        )
    if not db_path.exists():
        status["recommendations"].append("STOM DB was not found. Check _database/stock_tick_back.db.")

    if CustomFinetuneConfig is not None and config_path.exists():
        try:
            cfg = CustomFinetuneConfig(str(config_path))
            status["config_summary"] = {
                "data_path": cfg.data_path,
                "dataset_type": getattr(cfg, "dataset_type", None),
                "lookback_window": cfg.lookback_window,
                "predict_window": cfg.predict_window,
                "batch_size": cfg.batch_size,
                "basemodel_epochs": cfg.basemodel_epochs,
                "pretrained_tokenizer_path": cfg.pretrained_tokenizer_path,
                "pretrained_predictor_path": cfg.pretrained_predictor_path,
            }
        except Exception as exc:
            status["config_summary_error"] = str(exc)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    return status


def build_commands(
    db_path: Path = DEFAULT_DB_PATH,
    pilot_csv: Path = DEFAULT_PILOT_CSV,
    config_path: Path = DEFAULT_CONFIG_PATH,
    lookback_window: int = 300,
    predict_window: int = 60,
    max_tables: int = 100,
    price_mode: str = "close_only",
) -> Dict[str, str]:
    db = str(db_path)
    csv = str(pilot_csv)
    cfg = str(config_path)
    return {
        "1_env_check": "python finetune_csv/stom_ohlcv_pipeline.py env-check",
        "2_inspect": (
            f"python finetune_csv/prepare_stom_1tick.py inspect --db {db} "
            f"--lookback-window {lookback_window} --predict-window {predict_window} "
            f"--max-tables 0 --price-mode {price_mode}"
        ),
        "3_export_pilot": (
            f"python finetune_csv/prepare_stom_1tick.py export --db {db} --output {csv} "
            f"--lookback-window {lookback_window} --predict-window {predict_window} "
            f"--max-tables {max_tables} --price-mode {price_mode}"
        ),
        "4_train_pilot": f"python finetune_csv/train_sequential.py --config {cfg}",
        "5_eval_baseline_or_model": (
            f"python finetune_csv/stom_prediction_eval.py --data {csv} "
            f"--output webui/stom_predictions/pilot_predictions.csv "
            f"--lookback-window {lookback_window} --predict-window {predict_window} "
            "--max-windows 20 --mode baseline"
        ),
        "6_dashboard": "python webui/run.py  # open http://localhost:7070/stom",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="STOM OHLCV Kronos training pipeline helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    env_parser = subparsers.add_parser("env-check", help="Check environment readiness.")
    env_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    env_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    env_parser.add_argument("--json-output", default=None)

    commands_parser = subparsers.add_parser("commands", help="Print the recommended staged commands.")
    commands_parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    commands_parser.add_argument("--pilot-csv", default=str(DEFAULT_PILOT_CSV))
    commands_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    commands_parser.add_argument("--lookback-window", type=int, default=300)
    commands_parser.add_argument("--predict-window", type=int, default=60)
    commands_parser.add_argument("--max-tables", type=int, default=100)
    commands_parser.add_argument("--price-mode", choices=["close_only", "db_ohlc"], default="close_only")

    args = parser.parse_args(argv)

    if args.command == "env-check":
        payload = env_check(
            db_path=Path(args.db),
            config_path=Path(args.config),
            output_path=Path(args.json_output) if args.json_output else None,
        )
    else:
        payload = build_commands(
            db_path=Path(args.db),
            pilot_csv=Path(args.pilot_csv),
            config_path=Path(args.config),
            lookback_window=args.lookback_window,
            predict_window=args.predict_window,
            max_tables=args.max_tables,
            price_mode=args.price_mode,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
