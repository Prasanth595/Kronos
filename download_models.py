"""
Kronos Model Download Script
Downloads tokenizer and Kronos-small model from HuggingFace Hub.

Exit codes:
    0 -- download + smoke test succeeded
    1 -- failure (missing submodule, import error, or download error)
"""
import argparse
import sys
from pathlib import Path

KRONOS_DIR = Path(__file__).resolve().parent
MODEL_DIR = KRONOS_DIR / "model"

DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_MODEL = "NeoQuasar/Kronos-small"


def _check_model_package() -> None:
    if not MODEL_DIR.is_dir():
        print("[ERROR] Kronos model package not found at", MODEL_DIR)
        print("Hint: Ensure the Kronos submodule is initialized:")
        print("      git submodule update --init Kronos")
        sys.exit(1)


def _import_model():
    """Import Kronos/KronosTokenizer with a human-readable failure path."""
    _check_model_package()
    if str(KRONOS_DIR) not in sys.path:
        sys.path.insert(0, str(KRONOS_DIR))
    try:
        from model import Kronos, KronosTokenizer

        return Kronos, KronosTokenizer
    except ImportError as e:
        print(f"[ERROR] Failed to import Kronos model: {e}")
        print("Hint: Ensure dependencies are installed "
              "(pip install -r Kronos/requirements.txt) and the Kronos")
        print("      submodule is initialized (git submodule update --init).")
        sys.exit(1)


def _device_label(obj) -> str:
    """Best-effort device string. Works for nn.Module, degrades gracefully."""
    if hasattr(obj, "parameters"):
        try:
            return str(next(obj.parameters()).device)
        except (StopIteration, AttributeError):
            return "unknown"
    return "N/A (non-torch backend)"


def _smoke_test(model, tokenizer) -> bool:
    """
    Verify the downloaded artifacts load and produce a forward pass.

    Kronos is a time-series foundation model: the tokenizer consumes a numeric
    tensor and Kronos consumes token-id tensors, so the smoke test uses
    synthetic tensors rather than text.
    """
    print("\n[Verify] Running smoke test...")
    try:
        import torch

        # Tokenizer: forward pass on a synthetic time-series batch.
        d_in = tokenizer.embed.in_features
        x = torch.randn(1, 64, d_in)
        with torch.no_grad():
            tokenizer(x)
        print("        [OK] Tokenizer forward pass succeeded")

        # Model: forward pass on random token ids.
        s1_vocab = getattr(model, "s1_vocab_size", 4096)
        s2_vocab = getattr(model, "s2_vocab_size", 4096)
        s1_ids = torch.randint(0, s1_vocab, (1, 64))
        s2_ids = torch.randint(0, s2_vocab, (1, 64))
        with torch.no_grad():
            model(s1_ids, s2_ids)
        print("        [OK] Model forward pass succeeded")
        return True
    except Exception as e:
        print(f"        [FAIL] Smoke test failed: {e}")
        return False


def download_models(
    tokenizer_name: str = DEFAULT_TOKENIZER,
    model_name: str = DEFAULT_MODEL,
) -> bool:
    """
    Download the tokenizer and model, then verify them with a smoke test.

    Returns True on success; on failure prints an error and returns False.
    """
    print("=" * 50)
    print("Kronos Model Downloader")
    print("=" * 50)

    model_cls, tokenizer_cls = _import_model()

    print("\n[1/2] Downloading KronosTokenizer...")
    print(f"       Model: {tokenizer_name}")
    try:
        tokenizer = tokenizer_cls.from_pretrained(tokenizer_name)
    except Exception as e:
        print(f"[ERROR] Tokenizer download failed: {e}")
        return False
    print("       [OK] Tokenizer downloaded successfully")

    print("\n[2/2] Downloading Kronos model...")
    print(f"       Model: {model_name}")
    try:
        model = model_cls.from_pretrained(model_name)
    except Exception as e:
        print(f"[ERROR] Model download failed: {e}")
        return False
    print("       [OK] Model downloaded successfully")

    ok = _smoke_test(model, tokenizer)

    print("\n" + "=" * 50)
    if ok:
        print("Download complete!")
    else:
        print("Download complete, but the smoke test failed -- the cached")
        print("artifacts may be corrupt. Re-run to re-download them.")
    print(f"Model device: {_device_label(model)}")
    print(f"Tokenizer device: {_device_label(tokenizer)}")
    print("=" * 50)
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download Kronos models from HuggingFace Hub"
    )
    parser.add_argument("--tokenizer", default=DEFAULT_TOKENIZER, help="HF tokenizer repo id")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HF model repo id")
    args = parser.parse_args()

    success = download_models(args.tokenizer, args.model)
    sys.exit(0 if success else 1)
