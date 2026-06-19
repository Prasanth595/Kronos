"""Aggregate STOM RL baseline and learned-policy artifacts into one leaderboard."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


DEFAULT_BASELINE_REPORT = (
    Path("webui") / "rl_runs" / "stom_1s_2025_baseline_leaderboard_full_test" / "leaderboard_report.json"
)
DEFAULT_CONTEXTUAL_BANDIT_REPORT = (
    Path("webui") / "rl_runs" / "stom_1s_2025_contextual_bandit_full_test" / "eval_summary.json"
)
DEFAULT_SB3_SMOKE_REPORT = Path("webui") / "rl_runs" / "stom_1s_2025_sb3_smoke" / "sb3_smoke_summary.json"
DEFAULT_RL_RUNS_DIR = Path("webui") / "rl_runs"
AUTO_SB3_REPORTS = "__auto__"
DEFAULT_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_1s_2025_performance_leaderboard_full_test"


@dataclass(frozen=True)
class PerformanceLeaderboardConfig:
    baseline_report: str = str(DEFAULT_BASELINE_REPORT)
    contextual_bandit_report: str = str(DEFAULT_CONTEXTUAL_BANDIT_REPORT)
    sb3_smoke_reports: Tuple[str, ...] = (AUTO_SB3_REPORTS,)
    sb3_report_root: str = str(DEFAULT_RL_RUNS_DIR)
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    target_cost_bps: float = 25.0
    target_slippage_bps: float = 0.0
    write_artifacts: bool = True


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _float_or_zero(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def discover_sb3_summary_reports(root: Path = DEFAULT_RL_RUNS_DIR) -> Tuple[str, ...]:
    """Discover SB3 smoke/mini/short training summaries under the RL run root."""

    if not root.is_dir():
        return (str(DEFAULT_SB3_SMOKE_REPORT),) if DEFAULT_SB3_SMOKE_REPORT.is_file() else ()
    reports = sorted(
        {
            path
            for path in root.glob("stom_1s_2025_sb3*/sb3_smoke_summary.json")
            if path.is_file()
        },
        key=lambda path: (path.parent.name, path.name),
    )
    return tuple(str(path) for path in reports)


def _resolve_sb3_reports(config: PerformanceLeaderboardConfig) -> Tuple[Tuple[str, ...], str]:
    raw_reports = tuple(part.strip() for part in config.sb3_smoke_reports if str(part).strip())
    if any(part.lower() in {AUTO_SB3_REPORTS, "auto", "*"} for part in raw_reports):
        reports = discover_sb3_summary_reports(Path(config.sb3_report_root))
        return reports, "auto"
    return raw_reports, "explicit"


def _sb3_model_name(row: Mapping[str, Any]) -> str:
    if _bool_value(row.get("eval_only")):
        return str(row.get("model"))
    algorithm = str(row.get("algorithm") or row.get("model") or "sb3").lower()
    explicit = str(row.get("model") or f"{algorithm}_smoke")
    timesteps = int(_float_or_zero(row.get("training_timesteps")))
    if timesteps >= 1000:
        suffix = f"{timesteps // 1000}k" if timesteps % 1000 == 0 else str(timesteps)
        return f"{algorithm}_{suffix}"
    return explicit


def _sb3_run_category(row: Mapping[str, Any]) -> str:
    timesteps = int(_float_or_zero(row.get("training_timesteps")))
    if timesteps <= 1000:
        return "smoke"
    if timesteps <= 10_000:
        return "mini"
    if timesteps <= 100_000:
        return "short"
    return "long"


def _baseline_rows(payload: Mapping[str, Any], config: PerformanceLeaderboardConfig) -> List[Dict[str, Any]]:
    rows = payload.get("summary", {}).get("target_rows") or []
    normalized = []
    for row in rows:
        normalized.append(
            {
                "source": "baseline",
                "run_name": Path(config.baseline_report).parent.name,
                "model": str(row.get("policy") or "baseline"),
                "policy": str(row.get("policy") or "baseline"),
                "split": "test",
                "cost_bps": _float_or_zero(row.get("cost_bps", config.target_cost_bps)),
                "slippage_bps": _float_or_zero(row.get("slippage_bps", config.target_slippage_bps)),
                "episode_count": int(_float_or_zero(row.get("episode_count"))),
                "trade_count": int(_float_or_zero(row.get("trade_count"))),
                "trades_per_episode": _float_or_zero(row.get("trades_per_episode")),
                "avg_episode_net_return_pct": _float_or_zero(row.get("avg_episode_net_return_pct")),
                "median_episode_net_return_pct": _float_or_zero(row.get("median_episode_net_return_pct")),
                "compounded_return_pct": _float_or_zero(row.get("compounded_return_pct")),
                "avg_trade_net_return_pct": _float_or_zero(row.get("avg_trade_net_return_pct")),
                "hit_rate": _float_or_zero(row.get("hit_rate")),
                "max_drawdown_pct": _float_or_zero(row.get("max_drawdown_pct")),
                "positive_session_rate": _float_or_zero(row.get("positive_session_rate")),
                "passes_cost_gate": False,
                "is_smoke": False,
            }
        )
    return normalized


def _contextual_bandit_row(payload: Mapping[str, Any], config: PerformanceLeaderboardConfig) -> Dict[str, Any]:
    summary = payload.get("eval_summary", {}).get("summary") or payload.get("summary") or payload.get("eval_summary") or {}
    return {
        "source": "rl_model",
        "run_name": Path(config.contextual_bandit_report).parent.name,
        "model": "contextual_bandit",
        "policy": str(summary.get("policy") or "contextual_bandit"),
        "split": str(summary.get("eval_split") or "test"),
        "cost_bps": _float_or_zero(summary.get("cost_bps", config.target_cost_bps)),
        "slippage_bps": _float_or_zero(summary.get("slippage_bps", config.target_slippage_bps)),
        "episode_count": int(_float_or_zero(summary.get("episode_count"))),
        "trade_count": int(_float_or_zero(summary.get("trade_count"))),
        "trades_per_episode": _float_or_zero(summary.get("trades_per_episode")),
        "avg_episode_net_return_pct": _float_or_zero(summary.get("avg_episode_net_return_pct")),
        "median_episode_net_return_pct": _float_or_zero(summary.get("median_episode_net_return_pct")),
        "compounded_return_pct": _float_or_zero(summary.get("compounded_return_pct")),
        "avg_trade_net_return_pct": _float_or_zero(summary.get("avg_trade_net_return_pct")),
        "hit_rate": _float_or_zero(summary.get("hit_rate")),
        "max_drawdown_pct": _float_or_zero(summary.get("max_drawdown_pct")),
        "positive_session_rate": None,
        "passes_cost_gate": _bool_value(summary.get("passes_cost_gate")),
        "is_smoke": False,
    }


def _sb3_smoke_rows(
    payload: Mapping[str, Any],
    report_path: Path,
    config: PerformanceLeaderboardConfig,
) -> List[Dict[str, Any]]:
    rows = payload.get("models") or payload.get("model_summaries") or []
    normalized = []
    for row in rows:
        algorithm = str(row.get("algorithm") or row.get("model") or "sb3")
        run_category = _sb3_run_category(row)
        eval_only = _bool_value(row.get("eval_only"))
        normalized.append(
            {
                "source": "rl_model",
                "run_name": report_path.parent.name,
                "model": _sb3_model_name(row),
                "base_model": str(row.get("model") or f"{algorithm}_smoke"),
                "policy": str(row.get("policy") or f"stable_baselines3_{algorithm}"),
                "split": str(row.get("eval_split") or row.get("split") or "test"),
                "training_timesteps": int(_float_or_zero(row.get("training_timesteps"))),
                "run_category": run_category,
                "cost_bps": _float_or_zero(row.get("cost_bps", config.target_cost_bps)),
                "slippage_bps": _float_or_zero(row.get("slippage_bps", config.target_slippage_bps)),
                "episode_count": int(_float_or_zero(row.get("episode_count"))),
                "trade_count": int(_float_or_zero(row.get("trade_count"))),
                "trades_per_episode": _float_or_zero(row.get("trades_per_episode")),
                "avg_episode_net_return_pct": _float_or_zero(row.get("avg_episode_net_return_pct")),
                "median_episode_net_return_pct": _float_or_zero(row.get("median_episode_net_return_pct")),
                "compounded_return_pct": _float_or_zero(row.get("compounded_return_pct")),
                "avg_trade_net_return_pct": _float_or_zero(row.get("avg_trade_net_return_pct")),
                "hit_rate": _float_or_zero(row.get("hit_rate")),
                "max_drawdown_pct": _float_or_zero(row.get("max_drawdown_pct")),
                "positive_session_rate": None,
                "passes_cost_gate": _bool_value(row.get("passes_cost_gate")),
                "is_smoke": (run_category == "smoke") and not eval_only,
                "eval_only": eval_only,
                "source_run": row.get("source_run"),
                "source_model": row.get("source_model"),
                "eval_episode_count": int(_float_or_zero(row.get("eval_episode_count"))),
            }
        )
    return normalized


def _decision(row: Mapping[str, Any], *, no_trade_return: float, buy_and_hold_return: float) -> Dict[str, Any]:
    avg_return = _float_or_zero(row.get("avg_episode_net_return_pct"))
    mdd = _float_or_zero(row.get("max_drawdown_pct"))
    beats_no_trade = avg_return > no_trade_return
    beats_buy_and_hold = avg_return > buy_and_hold_return
    passes_cost_gate = _bool_value(row.get("passes_cost_gate"))
    if row.get("source") == "baseline":
        label = "baseline"
        reason = "비교 기준선"
    elif beats_buy_and_hold and passes_cost_gate:
        label = "candidate"
        reason = "25bp 비용 기준에서 buy-and-hold와 cost gate를 모두 통과"
    elif beats_no_trade:
        label = "watch"
        reason = "no-trade보다 낫지만 buy-and-hold 또는 cost gate 기준은 미달"
    else:
        label = "hold"
        reason = "비용 반영 후 no-trade 기준도 충분히 넘지 못함"
    if mdd <= -50.0 and label == "candidate":
        label = "watch"
        reason = "수익 기준은 통과했지만 MDD가 과도함"
    return {
        "beats_no_trade": beats_no_trade,
        "beats_buy_and_hold": beats_buy_and_hold,
        "usability": label,
        "decision_reason": reason,
    }


def build_performance_leaderboard(config: PerformanceLeaderboardConfig) -> Dict[str, Any]:
    baseline_payload = _read_json(Path(config.baseline_report))
    contextual_payload = _read_json(Path(config.contextual_bandit_report))
    rows = _baseline_rows(baseline_payload, config) + [_contextual_bandit_row(contextual_payload, config)]
    missing_optional_reports = []
    sb3_report_paths, sb3_report_source = _resolve_sb3_reports(config)
    for raw_report_path in sb3_report_paths:
        report_path = Path(raw_report_path)
        if not report_path.is_file():
            missing_optional_reports.append(str(report_path))
            continue
        rows.extend(_sb3_smoke_rows(_read_json(report_path), report_path, config))

    no_trade_return = next(
        (_float_or_zero(row.get("avg_episode_net_return_pct")) for row in rows if row.get("policy") == "no_trade"),
        0.0,
    )
    buy_and_hold_return = next(
        (_float_or_zero(row.get("avg_episode_net_return_pct")) for row in rows if row.get("policy") == "buy_and_hold"),
        0.0,
    )
    for row in rows:
        row.update(_decision(row, no_trade_return=no_trade_return, buy_and_hold_return=buy_and_hold_return))

    rows.sort(key=lambda row: _float_or_zero(row.get("avg_episode_net_return_pct")), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    model_rows = [row for row in rows if row.get("source") == "rl_model"]
    sb3_training_rows = [
        row
        for row in model_rows
        if not row.get("is_smoke")
        and not row.get("eval_only")
        and int(_float_or_zero(row.get("training_timesteps"))) > 0
    ]
    best_model = model_rows[0] if model_rows else None
    payload = {
        "mode": "stom_rl_performance_leaderboard",
        "config": {
            **asdict(config),
            "sb3_smoke_reports": list(sb3_report_paths),
            "sb3_smoke_reports_source": sb3_report_source,
        },
        "summary": {
            "row_count": len(rows),
            "target_cost_bps": config.target_cost_bps,
            "target_slippage_bps": config.target_slippage_bps,
            "best_policy": rows[0]["policy"] if rows else None,
            "best_rl_model": best_model["model"] if best_model else None,
            "best_rl_usability": best_model["usability"] if best_model else None,
            "buy_and_hold_avg_episode_net_return_pct": buy_and_hold_return,
            "no_trade_avg_episode_net_return_pct": no_trade_return,
            "rl_models_beating_buy_and_hold": [
                row["model"] for row in model_rows if row.get("beats_buy_and_hold")
            ],
            "rl_models_passing_cost_gate": [
                row["model"] for row in model_rows if row.get("passes_cost_gate")
            ],
            "rl_smoke_models": [
                row["model"] for row in model_rows if row.get("is_smoke")
            ],
            "rl_eval_only_models": [
                row["model"] for row in model_rows if row.get("eval_only")
            ],
            "rl_training_models": [
                row["model"] for row in sb3_training_rows
            ],
            "max_sb3_training_timesteps": max(
                [int(_float_or_zero(row.get("training_timesteps"))) for row in model_rows],
                default=0,
            ),
            "missing_optional_reports": missing_optional_reports,
        },
        "leaderboard": rows,
        "artifacts": {
            "output_dir": str(Path(config.output_dir)),
            "leaderboard_json": str(Path(config.output_dir) / "performance_leaderboard.json"),
            "leaderboard_csv": str(Path(config.output_dir) / "performance_leaderboard.csv"),
        },
    }
    if config.write_artifacts:
        output_dir = Path(config.output_dir)
        _write_json(output_dir / "performance_leaderboard.json", payload)
        _write_csv(
            output_dir / "performance_leaderboard.csv",
            rows,
            [
                "rank",
                "source",
                "run_name",
                "model",
                "base_model",
                "policy",
                "split",
                "training_timesteps",
                "run_category",
                "cost_bps",
                "slippage_bps",
                "episode_count",
                "trade_count",
                "trades_per_episode",
                "avg_episode_net_return_pct",
                "median_episode_net_return_pct",
                "compounded_return_pct",
                "avg_trade_net_return_pct",
                "hit_rate",
                "max_drawdown_pct",
                "positive_session_rate",
                "passes_cost_gate",
                "is_smoke",
                "eval_only",
                "source_run",
                "source_model",
                "beats_no_trade",
                "beats_buy_and_hold",
                "usability",
                "decision_reason",
            ],
        )
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> PerformanceLeaderboardConfig:
    parser = argparse.ArgumentParser(description="Aggregate STOM RL full-test performance leaderboard artifacts.")
    parser.add_argument("--baseline-report", default=str(DEFAULT_BASELINE_REPORT))
    parser.add_argument("--contextual-bandit-report", default=str(DEFAULT_CONTEXTUAL_BANDIT_REPORT))
    parser.add_argument(
        "--sb3-smoke-reports",
        default="auto",
        help=(
            "Comma-separated optional SB3 summary JSON paths. "
            "Use 'auto' to discover webui/rl_runs/stom_1s_2025_sb3*/sb3_smoke_summary.json."
        ),
    )
    parser.add_argument("--sb3-report-root", default=str(DEFAULT_RL_RUNS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--target-cost-bps", type=float, default=25.0)
    parser.add_argument("--target-slippage-bps", type=float, default=0.0)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return PerformanceLeaderboardConfig(
        baseline_report=args.baseline_report,
        contextual_bandit_report=args.contextual_bandit_report,
        sb3_smoke_reports=tuple(part.strip() for part in args.sb3_smoke_reports.split(",") if part.strip()),
        sb3_report_root=args.sb3_report_root,
        output_dir=args.output_dir,
        target_cost_bps=args.target_cost_bps,
        target_slippage_bps=args.target_slippage_bps,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = build_performance_leaderboard(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
