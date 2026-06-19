"""Predictor-stage handoff overrides for long-running STOM fine-tuning runs.

This module is intentionally torch-free so the handoff policy can be tested
without importing PyTorch while a separate long-running CUDA job is active.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, MutableMapping, Optional


DEFAULT_HANDOFF_FILENAME = "predictor_handoff_overrides.json"
INT_OVERRIDE_KEYS = {"batch_size", "num_workers"}


def default_handoff_path(save_path: str | os.PathLike[str]) -> Path:
    """Return the default handoff file path inside a run directory."""

    return Path(save_path) / DEFAULT_HANDOFF_FILENAME


def resolve_handoff_path(config: Any) -> Optional[Path]:
    """Resolve the predictor handoff file path for a Config object or dict."""

    explicit = os.getenv("KRONOS_PREDICTOR_HANDOFF_OVERRIDES")
    if explicit:
        return Path(explicit)

    save_path = _get_config_value(config, "save_path")
    if not save_path:
        return None
    return default_handoff_path(str(save_path))


def apply_predictor_handoff_overrides(config: Any, path: Optional[Path] = None) -> Dict[str, Any]:
    """Apply safe predictor-only overrides from JSON to a Config object or dict.

    Supported JSON shape:

    ```json
    {
      "enabled": true,
      "batch_size": 16,
      "num_workers": 2
    }
    ```

    Unknown keys are ignored. Values are validated as integers. The function
    returns metadata about whether anything was applied so callers can log it.
    """

    resolved_path = path or resolve_handoff_path(config)
    result: Dict[str, Any] = {
        "path": str(resolved_path) if resolved_path else None,
        "exists": bool(resolved_path and resolved_path.exists()),
        "enabled": False,
        "applied": {},
        "ignored": {},
    }
    if not resolved_path or not resolved_path.exists():
        _set_config_value(config, "predictor_handoff_overrides", result)
        return result

    payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Predictor handoff override must be a JSON object: {resolved_path}")

    enabled = bool(payload.get("enabled", True))
    result["enabled"] = enabled
    if not enabled:
        _set_config_value(config, "predictor_handoff_overrides", result)
        return result

    for key in INT_OVERRIDE_KEYS:
        if key not in payload:
            continue
        value = _parse_int_override(key, payload[key], resolved_path)
        _set_config_value(config, key, value)
        result["applied"][key] = value

    for key in payload:
        if key not in INT_OVERRIDE_KEYS and key != "enabled":
            result["ignored"][key] = payload[key]

    _set_config_value(config, "predictor_handoff_overrides", result)
    return result


def _parse_int_override(key: str, value: Any, path: Path) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{key} in {path} must be an integer, not boolean")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} in {path} must be an integer") from exc
    if key == "batch_size" and parsed <= 0:
        raise ValueError(f"{key} in {path} must be > 0")
    if key == "num_workers" and parsed < 0:
        raise ValueError(f"{key} in {path} must be >= 0")
    return parsed


def _get_config_value(config: Any, key: str) -> Any:
    if isinstance(config, MutableMapping):
        return config.get(key)
    return getattr(config, key, None)


def _set_config_value(config: Any, key: str, value: Any) -> None:
    if isinstance(config, MutableMapping):
        config[key] = value
    else:
        setattr(config, key, value)
