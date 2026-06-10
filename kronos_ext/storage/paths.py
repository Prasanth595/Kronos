"""Path helpers for local extension artifacts."""

from __future__ import annotations

from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("outputs") / "kronos_ext"


def ensure_output_dir(path: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """Create and return an output directory for local artifacts."""

    path.mkdir(parents=True, exist_ok=True)
    return path
