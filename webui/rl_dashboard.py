"""Read-only dashboard helpers for independent STOM RL artifacts.

The implementation is split by responsibility so path safety, run details,
table readers, and progress synthesis remain reviewable.  This module preserves
legacy imports and test monkeypatching of ``RL_RUN_ROOTS``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from . import rl_dashboard_files as _files
    from . import rl_dashboard_progress as _progress
    from . import rl_dashboard_runs as _runs
    from . import rl_dashboard_tables as _tables
except ImportError:  # pragma: no cover - supports direct script-style imports
    import rl_dashboard_files as _files
    import rl_dashboard_progress as _progress
    import rl_dashboard_runs as _runs
    import rl_dashboard_tables as _tables

REPO_ROOT = _files.REPO_ROOT
WEBUI_ROOT = _files.WEBUI_ROOT
MAX_TABLE_LIMIT = _files.MAX_TABLE_LIMIT
RL_RUN_ROOTS = _files.RL_RUN_ROOTS


def _sync_roots() -> None:
    _files.RL_RUN_ROOTS = [Path(root) for root in RL_RUN_ROOTS]


def iter_run_dirs() -> Iterable[Path]:
    _sync_roots()
    return _runs.iter_run_dirs()


def list_rl_runs(limit: int = 50) -> List[Dict[str, Any]]:
    _sync_roots()
    return _runs.list_rl_runs(limit=limit)


def resolve_run_dir(run_name: str) -> Path:
    _sync_roots()
    return _runs.resolve_run_dir(run_name)


def load_rl_run(run_name: str) -> Dict[str, Any]:
    _sync_roots()
    return _runs.load_rl_run(run_name)


def load_rl_table(run_name: str, table_name: str, *, policy: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
    _sync_roots()
    return _tables.load_rl_table(run_name, table_name, policy=policy, limit=limit)


def load_rl_cost_gate(run_name: str, *, limit: int = 500) -> Dict[str, Any]:
    _sync_roots()
    return _tables.load_rl_cost_gate(run_name, limit=limit)


def load_rl_events(run_name: str, *, limit: int = 500) -> Dict[str, Any]:
    _sync_roots()
    return _tables.load_rl_events(run_name, limit=limit)


def load_rl_progress() -> Dict[str, Any]:
    _sync_roots()
    return _progress.load_rl_progress()
