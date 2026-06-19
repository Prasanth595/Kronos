"""Tokenizer long-run safety helpers.

These helpers avoid importing torch so runner/dashboard tests can validate
checkpoint and OOM-recording behavior even on Python environments without a
working CUDA/PyTorch installation.
"""

from __future__ import annotations

import json
import os
from time import gmtime, strftime
from typing import Any, Optional


def resolve_tokenizer_validation_batch_size(config: dict[str, Any]) -> int:
    """Return a positive validation batch size, defaulting to training batch size."""

    raw_value = config.get("tokenizer_validation_batch_size", config["batch_size"])
    if raw_value in (None, ""):
        raw_value = config["batch_size"]
    return max(1, int(raw_value))


def unwrap_model(model: Any) -> Any:
    return model.module if hasattr(model, "module") else model


def save_tokenizer_checkpoint(
    model: Any,
    save_dir: str,
    checkpoint_name: str,
    rank: int,
    reason: str,
) -> Optional[str]:
    """Save a tokenizer checkpoint from rank 0 and return its path."""

    if rank != 0:
        return None
    save_path = os.path.join(save_dir, "checkpoints", checkpoint_name)
    unwrap_model(model).save_pretrained(save_path)
    print(f"Tokenizer checkpoint saved to {save_path} ({reason})")
    return save_path


def is_cuda_oom_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "cuda" in message and "out of memory" in message


def write_tokenizer_validation_failure(
    save_dir: str,
    epoch_idx: int,
    exc: BaseException,
    pre_validation_checkpoint: Optional[str],
    rank: int,
) -> Optional[str]:
    """Persist a small failure artifact so long-run OOMs are diagnosable."""

    if rank != 0:
        return None
    failure_path = os.path.join(save_dir, "validation_failure.json")
    payload = {
        "stage": "tokenizer_validation",
        "epoch": epoch_idx + 1,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "is_cuda_oom": is_cuda_oom_error(exc),
        "pre_validation_checkpoint": pre_validation_checkpoint,
        "created_at": strftime("%Y-%m-%dT%H-%M-%S", gmtime()),
    }
    with open(failure_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"Tokenizer validation failure artifact saved to {failure_path}")
    return failure_path
