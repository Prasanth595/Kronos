"""Utilities for resolving local or Hugging Face Kronos model sources."""

from pathlib import Path


def is_missing_local_model_path(model_path: str) -> bool:
    """Return True only when a path-like model source points to a missing local directory."""

    if not model_path:
        return True
    path = Path(model_path)
    looks_local = (
        path.is_absolute()
        or "\\" in model_path
        or model_path.startswith(".")
        or model_path.startswith("path/to/")
        or model_path.count("/") > 1
        or "/" not in model_path
    )
    return looks_local and not path.exists()


def resolve_model_source(primary_path: str, fallback_path: str, label: str, rank: int = 0) -> str:
    """Use a fine-tuned local model when present; otherwise fall back to a pretrained source."""

    if primary_path and not is_missing_local_model_path(primary_path):
        return primary_path
    if not fallback_path or is_missing_local_model_path(fallback_path):
        raise FileNotFoundError(
            f"{label} model source is not available. primary={primary_path!r}, fallback={fallback_path!r}"
        )
    if rank == 0:
        print(f"{label} local source not found; falling back to pretrained source: {fallback_path}")
    return fallback_path
