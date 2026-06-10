"""Serialization helpers for extension outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def write_json_result(path: Path, payload: Any) -> Path:
    """Write a JSON payload to disk.

    TODO: Add schema versioning before this is used by user-facing tooling.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(payload) if is_dataclass(payload) else payload
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
