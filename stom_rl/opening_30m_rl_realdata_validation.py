"""Cost-aware real-data validation gates for opening RL candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .opening_30m_rl_realdata import JsonValue


@dataclass(frozen=True, slots=True)
class RealdataGateInput:
    """Inputs required before a real-data opening candidate may be promoted."""

    candidate_net_return_pct: float
    no_trade_net_return_pct: float
    buy_and_hold_net_return_pct: float
    ts_imb_rule_net_return_pct: float
    cost_bps: float
    has_oos_split: bool
    has_negative_controls: bool
    negative_controls_passed: bool
    ablations: Mapping[str, bool]


def evaluate_realdata_candidate_gate(gate: RealdataGateInput) -> dict[str, JsonValue]:
    """Return a dashboard-readable NO-GO/INCONCLUSIVE/GO_CANDIDATE gate."""

    blocking_reasons: list[str] = []
    if not gate.has_oos_split:
        blocking_reasons.append("missing_oos_split")
    if not gate.has_negative_controls:
        blocking_reasons.append("missing_negative_controls")
    if gate.has_negative_controls and not gate.negative_controls_passed:
        blocking_reasons.append("failed_negative_controls")
    if float(gate.cost_bps) != 23.0:
        blocking_reasons.append("unexpected_cost_bps")

    baseline_results = _baseline_results(gate)
    for name, result in baseline_results.items():
        if not bool(result["passed"]):
            blocking_reasons.append(f"failed_baseline:{name}")

    feature_ablation_results = {
        name: {"passed": bool(passed), "required_for_go_candidate": True}
        for name, passed in sorted(gate.ablations.items())
    }
    for name, result in feature_ablation_results.items():
        if not bool(result["passed"]):
            blocking_reasons.append(f"failed_ablation:{name}")

    verdict = _verdict(blocking_reasons)
    return {
        "artifact_type": "opening_30m_realdata_validation_gate",
        "verdict": verdict,
        "can_show_go_candidate": verdict == "GO_CANDIDATE",
        "cost_bps": float(gate.cost_bps),
        "candidate_net_return_pct": float(gate.candidate_net_return_pct),
        "baseline_results": baseline_results,
        "feature_ablation_results": feature_ablation_results,
        "control_results": {
            "has_oos_split": bool(gate.has_oos_split),
            "has_negative_controls": bool(gate.has_negative_controls),
            "negative_controls_passed": bool(gate.negative_controls_passed),
        },
        "blocking_reasons": blocking_reasons,
        "guardrail": "GO_CANDIDATE is blocked unless OOS, controls, ablations, and 23bp baselines all pass.",
    }


def _baseline_results(gate: RealdataGateInput) -> dict[str, dict[str, JsonValue]]:
    baselines = {
        "no_trade": gate.no_trade_net_return_pct,
        "buy_and_hold": gate.buy_and_hold_net_return_pct,
        "ts_imb_rule": gate.ts_imb_rule_net_return_pct,
    }
    return {
        name: {
            "baseline_net_return_pct": float(value),
            "candidate_net_return_pct": float(gate.candidate_net_return_pct),
            "passed": float(gate.candidate_net_return_pct) > float(value),
            "is_reinforcement_learning": False,
            "label": "ts_imb RULE baseline" if name == "ts_imb_rule" else name,
        }
        for name, value in baselines.items()
    }


def _verdict(blocking_reasons: list[str]) -> str:
    if not blocking_reasons:
        return "GO_CANDIDATE"
    if any(reason.startswith("missing_") or reason == "unexpected_cost_bps" for reason in blocking_reasons):
        return "INCONCLUSIVE"
    return "NO-GO"
