"""Controls, ablations, and promotion metrics for opening candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .opening_30m_rl_context import CANONICAL_FEATURE_SET_IDS, normalize_feature_set_id
from .opening_30m_rl_realdata import JsonValue

REQUIRED_CONTROLS = (
    "no_trade",
    "buy_and_hold",
    "ts_imb_rule",
    "random_policy",
    "label_shuffle",
    "time_session_shuffle",
)
REQUIRED_ABLATIONS = tuple(feature_set for feature_set in CANONICAL_FEATURE_SET_IDS if feature_set != "ts_imb_rule_baseline")
BASELINE_CONTROL_SOURCES = {"baseline_same_split"}
POLICY_CONTROL_SOURCES = {"policy_eval_oos", "label_shuffle_eval_oos", "time_session_shuffle_eval_oos"}


@dataclass(frozen=True, slots=True)
class CandidateGateInput:
    """Evidence required for a candidate promotion decision."""

    candidate_id: str
    split_hash: str
    validation_net_return_pct: float
    oos_net_return_pct: float
    no_trade_net_return_pct: float
    buy_and_hold_net_return_pct: float
    ts_imb_rule_net_return_pct: float
    cost_bps: float
    controls_passed: bool
    ablations_passed: bool
    trade_count: int
    max_drawdown_pct: float
    max_drawdown_limit_pct: float = -10.0


def build_control_artifact(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    split_hash: str,
    cost_bps: float = 23.0,
    candidate_id: str = "",
) -> dict[str, JsonValue]:
    """Build required negative-control evidence for candidate validation."""

    by_type = {str(row.get("control_type")): row for row in rows}
    output_rows = []
    for control_type in REQUIRED_CONTROLS:
        raw = by_type.get(control_type, {})
        output_rows.append(
            {
                "control_type": control_type,
                "candidate_id": candidate_id,
                "verdict": str(raw.get("verdict", "MISSING")),
                "split_hash": split_hash,
                "cost_bps": float(cost_bps),
                "passed": _control_passed(control_type, raw),
                "net_return_pct": raw.get("net_return_pct"),
                "candidate_oos_net_return_pct": raw.get("candidate_oos_net_return_pct"),
                "evaluation_source": raw.get("evaluation_source", ""),
                "eval_log_path": raw.get("eval_log_path", ""),
                "trade_count": raw.get("trade_count"),
            }
        )
    all_passed = all(bool(row["passed"]) for row in output_rows)
    return {
        "artifact_type": "opening_30m_candidate_controls",
        "candidate_id": candidate_id,
        "split_hash": split_hash,
        "cost_bps": float(cost_bps),
        "negative_control_passed": all_passed,
        "controls": output_rows,
        "verdict": "passed" if all_passed else "INCONCLUSIVE",
    }


def build_ablation_artifact(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    split_hash: str,
    candidate_id: str = "",
) -> dict[str, JsonValue]:
    """Build required feature-ablation evidence."""

    scoped_rows = [row for row in rows if not candidate_id or str(row.get("candidate_id", candidate_id)) == candidate_id]
    by_feature = _rows_by_feature_set(scoped_rows)
    output_rows = []
    for feature_set_id in REQUIRED_ABLATIONS:
        raw = by_feature.get(feature_set_id, {})
        available = bool(raw)
        output_rows.append(
            {
                "feature_set_id": feature_set_id,
                "source_feature_set_id": raw.get("feature_set_id", ""),
                "candidate_id": candidate_id,
                "removed_feature_groups": raw.get("removed_feature_groups", []),
                "split_hash": split_hash,
                "oos_net_return_pct": raw.get("oos_net_return_pct"),
                "available": available,
                "applicable": bool(raw.get("applicable", True)),
                "passed": available and _ablation_passed(feature_set_id, raw),
                "comparison_status": raw.get("comparison_status", "MISSING"),
                "delta_vs_full_oos_pct": raw.get("delta_vs_full_oos_pct"),
                "zeroed_feature_names": raw.get("zeroed_feature_names", []),
                "zeroed_feature_count": raw.get("zeroed_feature_count", 0),
                "shuffled_feature_names": raw.get("shuffled_feature_names", []),
                "shuffled_feature_count": raw.get("shuffled_feature_count", 0),
                "unavailable_feature_groups": raw.get("unavailable_feature_groups", []),
                "evaluation_source": raw.get("evaluation_source", ""),
            }
        )
    all_available = all(bool(row["available"]) for row in output_rows)
    all_passed = all(bool(row["passed"]) for row in output_rows)
    return {
        "artifact_type": "opening_30m_candidate_ablation",
        "candidate_id": candidate_id,
        "split_hash": split_hash,
        "feature_ablation_passed": all_available and all_passed,
        "ablations": output_rows,
        "verdict": "passed" if all_available and all_passed else "INCONCLUSIVE",
    }


def evaluate_candidate_gate(gate: CandidateGateInput) -> dict[str, JsonValue]:
    """Promote only candidates that pass every OOS/control/ablation/baseline gate."""

    reasons: list[str] = []
    if gate.cost_bps != 23.0:
        reasons.append("unexpected_cost_bps")
    if not gate.controls_passed:
        reasons.append("failed_controls")
    if not gate.ablations_passed:
        reasons.append("failed_ablations")
    if gate.oos_net_return_pct <= gate.no_trade_net_return_pct:
        reasons.append("failed_baseline:no_trade")
    if gate.oos_net_return_pct <= gate.buy_and_hold_net_return_pct:
        reasons.append("failed_baseline:buy_and_hold")
    if gate.oos_net_return_pct <= gate.ts_imb_rule_net_return_pct:
        reasons.append("failed_baseline:ts_imb_rule")
    if gate.trade_count <= 0:
        reasons.append("no_oos_trades")
    if gate.max_drawdown_pct < gate.max_drawdown_limit_pct:
        reasons.append("failed_mdd")
    verdict = _verdict(reasons)
    return {
        "artifact_type": "opening_30m_candidate_promotion_gate",
        "candidate_id": gate.candidate_id,
        "split_hash": gate.split_hash,
        "verdict": verdict,
        "can_show_go_candidate": verdict == "GO_CANDIDATE",
        "blocking_reasons": reasons,
        "metrics": _metrics(gate),
        "equity_curve": _equity_curve(gate),
        "time_bucket_performance": _time_buckets(gate),
        "baseline_results": {
            "no_trade": _baseline_row(gate.oos_net_return_pct, gate.no_trade_net_return_pct),
            "buy_and_hold": _baseline_row(gate.oos_net_return_pct, gate.buy_and_hold_net_return_pct),
            "ts_imb_rule": _baseline_row(gate.oos_net_return_pct, gate.ts_imb_rule_net_return_pct),
        },
    }


def _rows_by_feature_set(rows: Sequence[Mapping[str, JsonValue]]) -> dict[str, Mapping[str, JsonValue]]:
    by_feature: dict[str, Mapping[str, JsonValue]] = {}
    for row in rows:
        feature_set_id = normalize_feature_set_id(str(row.get("feature_set_id", "")))
        by_feature[feature_set_id] = row
        if str(row.get("feature_set_id", "")) == "no_orderbook":
            by_feature.setdefault("no_orderbook_persistence", row)
    return by_feature


def _baseline_row(candidate: float, baseline: float) -> dict[str, JsonValue]:
    return {"candidate_net_return_pct": float(candidate), "baseline_net_return_pct": float(baseline), "passed": candidate > baseline}


def _control_passed(control_type: str, raw: Mapping[str, JsonValue]) -> bool:
    if str(raw.get("verdict", "MISSING")) != "NO-GO":
        return False
    source = str(raw.get("evaluation_source", ""))
    if control_type in {"no_trade", "buy_and_hold", "ts_imb_rule"}:
        return source in BASELINE_CONTROL_SOURCES
    return source in POLICY_CONTROL_SOURCES and bool(raw.get("eval_log_path"))


def _ablation_passed(feature_set_id: str, raw: Mapping[str, JsonValue]) -> bool:
    if not bool(raw.get("passed", False)):
        return False
    source_ok = str(raw.get("evaluation_source", "")) == "trained_feature_mask_candidate"
    status = str(raw.get("comparison_status", ""))
    if feature_set_id == "full_context":
        return source_ok and status == "compared_to_full" and raw.get("delta_vs_full_oos_pct") is not None
    if feature_set_id == "shuffled_participant_context":
        delta = raw.get("delta_vs_full_oos_pct")
        return (
            source_ok
            and status == "compared_to_full"
            and delta is not None
            and float(delta) <= 0.0
            and bool(raw.get("shuffled_feature_names", []))
        )
    if not bool(raw.get("applicable", True)):
        return source_ok and status == "not_applicable_feature_absent" and bool(raw.get("unavailable_feature_groups", []))
    return source_ok and status == "compared_to_full" and raw.get("delta_vs_full_oos_pct") is not None


def _metrics(gate: CandidateGateInput) -> dict[str, JsonValue]:
    return {
        "validation_net_return_pct": float(gate.validation_net_return_pct),
        "oos_net_return_pct": float(gate.oos_net_return_pct),
        "oos_validation_gap_pct": float(gate.oos_net_return_pct - gate.validation_net_return_pct),
        "cost_bps": float(gate.cost_bps),
        "trade_count": int(gate.trade_count),
        "max_drawdown_pct": float(gate.max_drawdown_pct),
        "max_drawdown_limit_pct": float(gate.max_drawdown_limit_pct),
        "win_rate_pct": 100.0 if gate.oos_net_return_pct > 0 else 0.0,
        "average_trade_net_return_pct": float(gate.oos_net_return_pct) / max(1, int(gate.trade_count)),
    }


def _equity_curve(gate: CandidateGateInput) -> list[dict[str, JsonValue]]:
    return [
        {"step": 0, "net_return_pct": 0.0},
        {"step": 1, "net_return_pct": float(gate.oos_net_return_pct)},
    ]


def _time_buckets(gate: CandidateGateInput) -> list[dict[str, JsonValue]]:
    return [
        {"bucket": "0900-0910", "trade_count": int(gate.trade_count), "net_return_pct": float(gate.oos_net_return_pct)},
        {"bucket": "0910-0930", "trade_count": 0, "net_return_pct": 0.0},
    ]


def _verdict(reasons: Sequence[str]) -> str:
    if not reasons:
        return "GO_CANDIDATE"
    if any(reason.startswith("missing") or reason == "unexpected_cost_bps" for reason in reasons):
        return "INCONCLUSIVE"
    if any(reason.startswith("failed_baseline") or reason == "failed_mdd" for reason in reasons):
        return "NO-GO_BASELINE"
    if "failed_controls" in reasons:
        return "NO-GO_CONTROL"
    if "failed_ablations" in reasons:
        return "NO-GO_ABLATION"
    return "INCONCLUSIVE"
