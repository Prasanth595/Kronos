"""JSONL event helpers for realtime STOM reinforcement-learning views."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


SCHEMA_VERSION = "stom_rl_live_event.v1"
ACTION_LABELS = {0: "hold", 1: "buy", 2: "sell"}
MAX_EVENT_LIMIT = 10_000


def utc_now_iso() -> str:
    """Return a compact timezone-aware UTC timestamp."""

    return datetime.now(tz=timezone.utc).isoformat()


def clean_json_value(value: Any) -> Any:
    """Convert numpy/scalar values to JSON-safe values and drop NaN/inf."""

    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return clean_json_value(value.item())
    if isinstance(value, Mapping):
        return {str(k): clean_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json_value(v) for v in value]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return number if math.isfinite(number) else None


def action_label(action: Any) -> str:
    """Return a stable label for a STOM discrete action."""

    try:
        return ACTION_LABELS.get(int(action), str(action))
    except (TypeError, ValueError):
        return str(action)


@dataclass(frozen=True)
class RlLiveEvent:
    """Single JSONL event consumed by the realtime RL dashboard."""

    run_id: str
    algorithm: str
    phase: str
    global_step: int
    action: Optional[int] = None
    reward: Optional[float] = None
    episode: Optional[int] = None
    episode_id: Optional[str] = None
    timestamp: Optional[str] = None
    price: Optional[float] = None
    position: Optional[float] = None
    equity: Optional[float] = None
    loss: Optional[float] = None
    exploration: Optional[float] = None
    source: str = "sb3_smoke"
    schema_version: str = SCHEMA_VERSION
    timestamp_utc: str = field(default_factory=utc_now_iso)
    info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["action_name"] = action_label(self.action) if self.action is not None else None
        return {key: clean_json_value(value) for key, value in payload.items()}


class RlLiveEventWriter:
    """Append-only JSONL writer for RL live events."""

    def __init__(self, path: str | Path, *, run_id: str, enabled: bool = True):
        self.path = Path(path)
        self.run_id = str(run_id)
        self.enabled = bool(enabled)

    def reset(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def write(self, event: RlLiveEvent | Mapping[str, Any]) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = event.to_dict() if isinstance(event, RlLiveEvent) else clean_json_value(dict(event))
        with self.path.open("a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def write_step(self, *, algorithm: str, phase: str, global_step: int, **kwargs: Any) -> None:
        self.write(
            RlLiveEvent(
                run_id=self.run_id,
                algorithm=str(algorithm),
                phase=str(phase),
                global_step=int(global_step),
                **kwargs,
            )
        )


def read_live_events(path: str | Path, *, limit: int = 500, tail: bool = True) -> Tuple[List[Dict[str, Any]], bool]:
    """Read JSONL events with a bounded limit and malformed-line tolerance."""

    path = Path(path)
    limit = max(0, min(int(limit), MAX_EVENT_LIMIT))
    if not path.is_file() or limit == 0:
        return [], False
    lines = path.read_text(encoding="utf-8").splitlines()
    truncated = len(lines) > limit
    source = reversed(lines) if tail else iter(lines)
    rows: List[Dict[str, Any]] = []
    for line in source:
        if len(rows) >= limit:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    if tail:
        rows.reverse()
    return rows, truncated


def summarize_live_events(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(events)
    phases = Counter(str(row.get("phase") or "unknown") for row in rows)
    algorithms = Counter(str(row.get("algorithm") or "unknown") for row in rows)
    actions = Counter(str(row.get("action_name") or action_label(row.get("action"))) for row in rows)
    rewards = [float(row["reward"]) for row in rows if row.get("reward") is not None]
    equities = [float(row["equity"]) for row in rows if row.get("equity") is not None]
    latest = rows[-1] if rows else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "event_count": len(rows),
        "phases": dict(sorted(phases.items())),
        "algorithms": dict(sorted(algorithms.items())),
        "actions": dict(sorted(actions.items())),
        "avg_reward": sum(rewards) / len(rewards) if rewards else 0.0,
        "latest_equity": equities[-1] if equities else None,
        "latest_event": dict(latest),
    }


def summarize_live_event_file(path: str | Path, *, limit: int = MAX_EVENT_LIMIT) -> Dict[str, Any]:
    rows, truncated = read_live_events(path, limit=limit, tail=False)
    summary = summarize_live_events(rows)
    summary["truncated"] = truncated
    return summary
