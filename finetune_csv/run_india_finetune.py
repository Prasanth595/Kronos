"""
End-to-end fine-tuning runner for Indian equity/index 5-min data (NSE/BSE).

Steps:
  1. Fetch data from yfinance  (skipped if CSV already exists)
  2. Fine-tune KronosTokenizer
  3. Fine-tune Kronos predictor

Usage:
  # Full pipeline — fetch NIFTY50 + top stocks, then train
  python run_india_finetune.py --tickers NIFTY50 RELIANCE TCS INFY HDFCBANK

  # Use an existing CSV
  python run_india_finetune.py --data_path data/india_5min.csv

  # Skip tokenizer (already done), only re-train predictor
  python run_india_finetune.py --tickers NIFTY50 --skip_tokenizer

  # Custom config
  python run_india_finetune.py --data_path data/india_5min.csv --config configs/config_india_5min.yaml
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list, desc: str):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    print(f"  CMD: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


def patch_config_data_path(config_path: str, data_path: str, out_path: str):
    """Write a copy of config_path with data.data_path replaced."""
    import yaml
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["data"]["data_path"] = os.path.abspath(data_path)
    with open(out_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, indent=2)


def ensure_config(script_dir: str, config_arg: str) -> str:
    """Return a config path, generating a minimal one if none exists."""
    if config_arg and os.path.exists(config_arg):
        return config_arg

    candidates = [
        os.path.join(script_dir, "configs", "config_india_5min.yaml"),
        os.path.join(script_dir, "configs", "config_us_5min.yaml"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # Generate minimal YAML
    import yaml
    path = os.path.join(script_dir, "configs", "config_india_5min.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cfg = {
        "data": {
            "data_path": "data/india_5min.csv",
            "lookback": 512,
            "pred_len": 20,
            "train_ratio": 0.7,
            "val_ratio": 0.15,
        },
        "tokenizer": {
            "pretrained": "NeoQuasar/Kronos-Tokenizer-base",
            "save_path": "finetuned/india_5min/tokenizer",
            "epochs": 10,
            "batch_size": 32,
            "lr": 1e-4,
        },
        "predictor": {
            "pretrained": "NeoQuasar/Kronos-base",
            "tokenizer_path": "finetuned/india_5min/tokenizer/best_model",
            "save_path": "finetuned/india_5min/basemodel",
            "epochs": 10,
            "batch_size": 16,
            "lr": 5e-5,
        },
    }
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, indent=2)
    print(f"  Generated minimal config → {path}")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Kronos Indian market (NSE/BSE) fine-tuning pipeline"
    )
    parser.add_argument(
        "--tickers", nargs="+", default=[],
        help="NSE symbols to fetch: RELIANCE, TCS, NIFTY50, BANKNIFTY, …"
    )
    parser.add_argument(
        "--period", default="60d",
        help="yfinance period (max 60d for 5-min interval). Default: 60d"
    )
    parser.add_argument(
        "--data_path", default="data/india_5min.csv",
        help="Path to existing or target CSV. Default: data/india_5min.csv"
    )
    parser.add_argument(
        "--config", default="",
        help="YAML config path. Auto-detected if omitted."
    )
    parser.add_argument("--skip_tokenizer", action="store_true",
                        help="Skip tokenizer training")
    parser.add_argument("--skip_predictor", action="store_true",
                        help="Skip predictor training")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path  = args.data_path if os.path.isabs(args.data_path) \
                 else os.path.join(script_dir, args.data_path)

    # ── 1. Fetch data ─────────────────────────────────────────────────────────
    if args.tickers:
        run(
            [sys.executable, os.path.join(script_dir, "fetch_india_data.py"),
             "--tickers", *args.tickers,
             "--period", args.period,
             "--output", data_path],
            f"Fetching 5-min data for: {', '.join(args.tickers)}"
        )
    else:
        if not os.path.exists(data_path):
            raise FileNotFoundError(
                f"No tickers provided and data file not found: {data_path}\n"
                "Pass --tickers RELIANCE TCS … to fetch data first."
            )
        print(f"Using existing data file: {data_path}")

    # ── 2. Resolve + patch config ─────────────────────────────────────────────
    config_src = ensure_config(script_dir, args.config)
    config_run = os.path.join(script_dir, "configs", "_run_india_config.yaml")
    os.makedirs(os.path.dirname(config_run), exist_ok=True)
    patch_config_data_path(config_src, data_path, config_run)
    print(f"Active config → {config_run}")

    finetune_dir      = os.path.join(script_dir, "..", "finetune")
    tokenizer_script  = os.path.join(finetune_dir, "train_tokenizer.py")
    predictor_script  = os.path.join(finetune_dir, "train_predictor.py")

    # ── 3. Fine-tune tokenizer ────────────────────────────────────────────────
    if not args.skip_tokenizer:
        if not os.path.exists(tokenizer_script):
            print(f"\n  WARNING: {tokenizer_script} not found.")
            print("  Run from inside the cloned Kronos repo.")
        else:
            run([sys.executable, tokenizer_script, "--config", config_run],
                "Stage 1 / 2 — Fine-tuning KronosTokenizer on Indian data")
    else:
        print("\nSkipping tokenizer training (--skip_tokenizer set).")

    # ── 4. Fine-tune predictor ────────────────────────────────────────────────
    if not args.skip_predictor:
        if not os.path.exists(predictor_script):
            print(f"\n  WARNING: {predictor_script} not found.")
        else:
            run([sys.executable, predictor_script, "--config", config_run],
                "Stage 2 / 2 — Fine-tuning Kronos predictor on Indian data")
    else:
        print("\nSkipping predictor training (--skip_predictor set).")

    print("\n" + "=" * 60)
    print("  Fine-tuning complete!")
    print("  Models saved under: finetuned/india_5min/")
    print("  Inference paths:")
    print("    tokenizer : finetuned/india_5min/tokenizer/best_model")
    print("    model     : finetuned/india_5min/basemodel/best_model")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
