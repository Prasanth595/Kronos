"""Publish the '시초 갭상승' (opening gap-up) RULE strategy backtest as a
read-only dashboard run for the STOM RL dashboard follow/replay view.

This is a RULE strategy backtest — it is NOT a reinforcement-learning policy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Re-use existing RL-event helpers (no duplication)
# ---------------------------------------------------------------------------
from stom_rl.rl_events import (
    RlLiveEvent,
    RlLiveEventWriter,
    summarize_live_events,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_INSTANCES = Path(".omx/artifacts/gap_up_backtest/instances.json")
_DEFAULT_OUTPUT_ROOT = Path("webui/rl_runs")
_DEFAULT_COST_BPS = 23.0
_DEFAULT_TP_SL_KEY = "tp5_sl1"
_DEFAULT_INITIAL_CASH = 1_000_000.0
_VALID_FILTERS = ("none", "ts", "ts_imb")


# ---------------------------------------------------------------------------
# Pure data helpers (small, immutable, no side effects)
# ---------------------------------------------------------------------------

def _load_instances(path: Path) -> List[Dict[str, Any]]:
    """Load instances.json with BOM-tolerant UTF-8 decoding."""
    if not path.is_file():
        raise FileNotFoundError(
            f"instances.json not found at {path!r}. "
            "Run the gap_up_backtest first to generate it."
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _apply_filter(
    records: List[Dict[str, Any]],
    filter_name: str,
) -> List[Dict[str, Any]]:
    """Return the subset of records that pass *filter_name*."""
    if filter_name == "none":
        return list(records)
    if filter_name == "ts":
        return [r for r in records if r.get("pass_ts")]
    if filter_name == "ts_imb":
        return [r for r in records if r.get("pass_ts_imb")]
    raise ValueError(
        f"Invalid filter {filter_name!r}. Choose from: {_VALID_FILTERS}"
    )


def _sort_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort deterministically by (session, symbol) ascending."""
    return sorted(records, key=lambda r: (str(r.get("session", "")), str(r.get("symbol", ""))))


def _net_at_cost(
    raw_net_pct: float,
    cost_bps: float,
    base_cost_bps: float = 25.0,
) -> float:
    """Adjust a cached net_pct (computed at base_cost_bps) to a target cost_bps."""
    return raw_net_pct + (base_cost_bps - cost_bps) / 100.0


def _build_equity_curve(
    records: List[Dict[str, Any]],
    *,
    tp_sl_key: str,
    cost_bps: float,
    initial_cash: float,
) -> Tuple[List[float], List[float], float]:
    """Build a non-compounded fixed-notional equity curve.

    Returns (net_per_trade, nav_series, final_cum_pct).
    """
    net_series: List[float] = []
    nav_series: List[float] = []
    cum_pct = 0.0
    for rec in records:
        raw = float(rec[f"{tp_sl_key}_net_pct"])
        net_i = _net_at_cost(raw, cost_bps)
        cum_pct += net_i
        nav_i = initial_cash * (1.0 + cum_pct / 100.0)
        net_series.append(net_i)
        nav_series.append(nav_i)
    return net_series, nav_series, cum_pct


def _compute_stats(
    net_series: List[float],
    nav_series: List[float],
    *,
    initial_cash: float,
) -> Dict[str, Any]:
    """Derive summary statistics from equity-curve vectors."""
    n = len(net_series)
    if n == 0:
        return {
            "total_net_pct": 0.0,
            "expectancy_pct": 0.0,
            "win_rate": 0.0,
            "max_drawdown_pct": 0.0,
            "max_losing_streak": 0,
            "final_nav": initial_cash,
        }

    total_net_pct = sum(net_series)
    expectancy_pct = total_net_pct / n
    win_rate = sum(1 for x in net_series if x > 0) / n

    # Max drawdown on cumulative-pct series
    cum_series = [sum(net_series[: i + 1]) for i in range(n)]
    running_peak = cum_series[0]
    max_dd = 0.0
    for cp in cum_series:
        if cp > running_peak:
            running_peak = cp
        dd = cp - running_peak
        if dd < max_dd:
            max_dd = dd

    # Max consecutive losing streak
    streak = 0
    max_streak = 0
    for x in net_series:
        if x <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        "total_net_pct": total_net_pct,
        "expectancy_pct": expectancy_pct,
        "win_rate": win_rate,
        "max_drawdown_pct": max_dd,
        "max_losing_streak": max_streak,
        "final_nav": nav_series[-1],
    }


def _make_iso_timestamp(session: Any) -> str:
    """Convert a session string like '20230906' to an ISO timestamp."""
    s = str(session)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}T09:25:00"
    return f"{s}T09:25:00"


def _build_event(
    *,
    run_name: str,
    filter_name: str,
    tp_sl_key: str,
    rec: Dict[str, Any],
    trade_idx: int,
    net_i: float,
    nav_i: float,
    cum_pct: float,
) -> RlLiveEvent:
    """Construct a single RlLiveEvent for one backtest trade."""
    session = rec.get("session", "")
    symbol = str(rec.get("symbol", ""))
    return RlLiveEvent(
        run_id=run_name,
        algorithm=f"rule:gap_up_{filter_name}",
        phase="backtest",
        global_step=trade_idx,
        action=1,
        reward=net_i / 100.0,
        timestamp=_make_iso_timestamp(session),
        price=float(rec.get("entry_price", 0.0) or 0.0),
        position=1.0,
        equity=nav_i,
        source="gap_up_backtest",
        info={
            "session": session,
            "symbol": symbol,
            "net_pct": net_i,
            "cum_net_pct": cum_pct,
            "exit_reason": rec.get(f"{tp_sl_key}_reason"),
            "filter": filter_name,
            "entry_change_rate": rec.get("entry_change_rate"),
            "trade_strength": rec.get("entry_trade_strength"),
            "bid_ask_imbalance": rec.get("entry_bid_ask_imbalance"),
            "nav": nav_i,
            "sizing": "fixed_notional_non_compounded",
            "note": "RULE strategy backtest, not an RL policy",
        },
    )


def _write_portfolio_paper_summary(
    output_dir: Path,
    *,
    run_name: str,
    filter_name: str,
    tp_sl_key: str,
    cost_bps: float,
    initial_cash: float,
    n: int,
    stats: Dict[str, Any],
) -> None:
    """Write portfolio_paper_summary.json — the dashboard detection anchor."""
    payload = {
        "run_id": run_name,
        "artifact_type": "portfolio_paper",
        "summary": {
            "strategy": (
                "시초 갭상승 (opening gap-up) RULE strategy — NOT reinforcement learning"
            ),
            "steps": n,
            "trade_count": n,
            "live_event_count": n,
            "final_nav": stats["final_nav"],
            "initial_cash": initial_cash,
            "total_net_pct": stats["total_net_pct"],
            "expectancy_pct": stats["expectancy_pct"],
            "win_rate": stats["win_rate"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
            "max_losing_streak": stats["max_losing_streak"],
            "cost_bps": cost_bps,
            "filter": filter_name,
            "tp_sl": "TP5%/SL1%/09:25",
        },
        "config": {
            "source": "stom_rl/gap_up_backtest.py instances.json",
            "filter": filter_name,
            "cost_bps": cost_bps,
            "tp_sl_key": tp_sl_key,
            "time_exit": "09:25",
            "initial_cash": initial_cash,
            "sizing": "fixed_notional_non_compounded",
            "is_reinforcement_learning": False,
            "note": (
                "RULE strategy (등락율>=2% + filter, fixed TP/SL); "
                "RL portfolio selection was separately proven to have NO intraday alpha."
            ),
        },
        "walk_forward_summary": {},
    }
    (output_dir / "portfolio_paper_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def _write_live_summary(
    output_dir: Path,
    events: List[Dict[str, Any]],
) -> None:
    """Write rl_live_summary.json from already-serialised event dicts."""
    summary = summarize_live_events(events)
    summary["truncated"] = False
    (output_dir / "rl_live_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def publish_gap_up_run(
    *,
    instances_path: Optional[Path] = None,
    filter_name: str = "ts_imb",
    cost_bps: float = _DEFAULT_COST_BPS,
    tp_sl_key: str = _DEFAULT_TP_SL_KEY,
    run_name: Optional[str] = None,
    output_root: Optional[Path] = None,
    initial_cash: float = _DEFAULT_INITIAL_CASH,
) -> Dict[str, Any]:
    """Publish the gap-up backtest as a dashboard run directory.

    Parameters
    ----------
    instances_path:
        Path to instances.json.  Defaults to the canonical artifact path.
    filter_name:
        One of ``"none"``, ``"ts"``, ``"ts_imb"``.
    cost_bps:
        Round-trip cost in basis points (default 23.0 — domestic broker).
    tp_sl_key:
        Key prefix in instances.json, e.g. ``"tp5_sl1"``.
    run_name:
        Output directory name under *output_root*.  Defaults to
        ``"gap_up_<filter>_equity"``.
    output_root:
        Root directory for RL runs.  Defaults to ``webui/rl_runs``.
    initial_cash:
        Starting capital for NAV calculations.

    Returns
    -------
    dict
        The portfolio_paper_summary payload (same dict written to disk).
    """
    if filter_name not in _VALID_FILTERS:
        raise ValueError(
            f"Invalid filter {filter_name!r}. Choose from: {_VALID_FILTERS}"
        )

    resolved_instances = Path(instances_path) if instances_path is not None else _DEFAULT_INSTANCES
    resolved_root = Path(output_root) if output_root is not None else _DEFAULT_OUTPUT_ROOT
    resolved_run_name = run_name or f"gap_up_{filter_name}_equity"

    raw_records = _load_instances(resolved_instances)
    filtered = _apply_filter(raw_records, filter_name)
    sorted_records = _sort_records(filtered)

    net_series, nav_series, _final_cum = _build_equity_curve(
        sorted_records,
        tp_sl_key=tp_sl_key,
        cost_bps=cost_bps,
        initial_cash=initial_cash,
    )

    stats = _compute_stats(net_series, nav_series, initial_cash=initial_cash)
    n = len(sorted_records)

    output_dir = resolved_root / resolved_run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write JSONL events
    event_path = output_dir / "rl_live_events.jsonl"
    writer = RlLiveEventWriter(event_path, run_id=resolved_run_name)
    writer.reset()

    serialised_events: List[Dict[str, Any]] = []
    cum_pct = 0.0
    for idx, (rec, net_i, nav_i) in enumerate(zip(sorted_records, net_series, nav_series), start=1):
        cum_pct += net_i
        event = _build_event(
            run_name=resolved_run_name,
            filter_name=filter_name,
            tp_sl_key=tp_sl_key,
            rec=rec,
            trade_idx=idx,
            net_i=net_i,
            nav_i=nav_i,
            cum_pct=cum_pct,
        )
        writer.write(event)
        serialised_events.append(event.to_dict())

    _write_live_summary(output_dir, serialised_events)
    _write_portfolio_paper_summary(
        output_dir,
        run_name=resolved_run_name,
        filter_name=filter_name,
        tp_sl_key=tp_sl_key,
        cost_bps=cost_bps,
        initial_cash=initial_cash,
        n=n,
        stats=stats,
    )

    return {
        "run_id": resolved_run_name,
        "artifact_type": "portfolio_paper",
        "summary": {
            "strategy": (
                "시초 갭상승 (opening gap-up) RULE strategy — NOT reinforcement learning"
            ),
            "steps": n,
            "trade_count": n,
            "live_event_count": n,
            "final_nav": stats["final_nav"],
            "initial_cash": initial_cash,
            "total_net_pct": stats["total_net_pct"],
            "expectancy_pct": stats["expectancy_pct"],
            "win_rate": stats["win_rate"],
            "max_drawdown_pct": stats["max_drawdown_pct"],
            "max_losing_streak": stats["max_losing_streak"],
            "cost_bps": cost_bps,
            "filter": filter_name,
            "tp_sl": "TP5%/SL1%/09:25",
        },
        "config": {
            "source": "stom_rl/gap_up_backtest.py instances.json",
            "filter": filter_name,
            "cost_bps": cost_bps,
            "tp_sl_key": tp_sl_key,
            "time_exit": "09:25",
            "initial_cash": initial_cash,
            "sizing": "fixed_notional_non_compounded",
            "is_reinforcement_learning": False,
            "note": (
                "RULE strategy (등락율>=2% + filter, fixed TP/SL); "
                "RL portfolio selection was separately proven to have NO intraday alpha."
            ),
        },
        "walk_forward_summary": {},
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish opening gap-up RULE backtest as a dashboard run."
    )
    parser.add_argument(
        "--instances",
        default=str(_DEFAULT_INSTANCES),
        help="Path to instances.json (default: %(default)s)",
    )
    parser.add_argument(
        "--filter",
        dest="filter_name",
        choices=list(_VALID_FILTERS),
        default="ts_imb",
        help="Entry filter (default: %(default)s)",
    )
    parser.add_argument(
        "--cost-bps",
        type=float,
        default=_DEFAULT_COST_BPS,
        help="Round-trip cost in bps (default: %(default)s)",
    )
    parser.add_argument(
        "--tp-sl-key",
        default=_DEFAULT_TP_SL_KEY,
        help="TP/SL key prefix in instances.json (default: %(default)s)",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Output run directory name (default: gap_up_<filter>_equity)",
    )
    parser.add_argument(
        "--output-root",
        default=str(_DEFAULT_OUTPUT_ROOT),
        help="Root directory for RL runs (default: %(default)s)",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=_DEFAULT_INITIAL_CASH,
        help="Starting capital for NAV (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    result = publish_gap_up_run(
        instances_path=Path(args.instances),
        filter_name=args.filter_name,
        cost_bps=args.cost_bps,
        tp_sl_key=args.tp_sl_key,
        run_name=args.run_name,
        output_root=Path(args.output_root),
        initial_cash=args.initial_cash,
    )

    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+, no-op if already utf-8
    except (AttributeError, ValueError):
        pass
    try:
        print(encoded)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(encoded.encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
