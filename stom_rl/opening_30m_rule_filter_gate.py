"""Promotion gate for opening RULE filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .opening_30m_rule_filter_contract import (
    VERDICT_GO_RULE_FILTER,
    VERDICT_INCONCLUSIVE,
    VERDICT_NO_GO_ABLATION,
    VERDICT_NO_GO_BASELINE,
    VERDICT_NO_GO_CONTROL,
    rule_filter_strategy_context,
)


EXPECTED_RULE_FILTER_COST_BPS = 23.0


@dataclass(frozen=True, slots=True)
class RuleFilterGateInput:
    """Evidence required for a RULE filter decision."""

    split_hash: str
    cost_bps: float
    validation_net_return_pct: float
    oos_net_return_pct: float
    no_trade_net_return_pct: float
    buy_and_hold_net_return_pct: float
    ts_imb_rule_net_return_pct: float
    controls_passed: bool
    ablations_passed: bool
    oos_take_count: int
    min_oos_take_count: int = 1
    max_drawdown_pct: float = 0.0
    max_allowed_drawdown_pct: float = 5.0
    skipped_opportunity_cost_pct: float = 0.0


def evaluate_rule_filter_gate(gate: RuleFilterGateInput) -> dict[str, Any]:
    """Promote only filters that beat baselines, controls, and ablations."""

    reasons = _blocking_reasons(gate)
    verdict = _verdict(reasons)
    return {
        "artifact_type": "opening_rule_filter_gate",
        "split_hash": gate.split_hash,
        "cost_bps": float(gate.cost_bps),
        "verdict": verdict,
        "can_show_go_rule_filter": verdict == VERDICT_GO_RULE_FILTER,
        "blocking_reasons": reasons,
        "metrics": _metrics(gate),
        "baseline_results": _baseline_results(gate),
        "equity_curve": _equity_curve(gate),
        "opportunity_cost_curve": _opportunity_cost_curve(gate),
        "time_bucket_performance": _time_buckets(gate),
        "strategy_context": rule_filter_strategy_context(),
    }


def _blocking_reasons(gate: RuleFilterGateInput) -> list[str]:
    reasons: list[str] = []
    if float(gate.cost_bps) != EXPECTED_RULE_FILTER_COST_BPS:
        reasons.append("failed_cost:expected_23bp")
    if gate.oos_take_count <= 0:
        reasons.append("no_oos_take_trades")
    if gate.oos_take_count < gate.min_oos_take_count:
        reasons.append("insufficient_oos_take_trades")
    if gate.max_drawdown_pct > gate.max_allowed_drawdown_pct:
        reasons.append("failed_risk:max_drawdown")
    if gate.oos_net_return_pct <= gate.no_trade_net_return_pct:
        reasons.append("failed_baseline:no_trade")
    if gate.oos_net_return_pct <= gate.buy_and_hold_net_return_pct:
        reasons.append("failed_baseline:buy_and_hold")
    if gate.oos_net_return_pct <= gate.ts_imb_rule_net_return_pct:
        reasons.append("failed_baseline:ts_imb_rule")
    if not gate.controls_passed:
        reasons.append("failed_controls")
    if not gate.ablations_passed:
        reasons.append("failed_ablations")
    return reasons


def _verdict(reasons: list[str]) -> str:
    if not reasons:
        return VERDICT_GO_RULE_FILTER
    if "failed_controls" in reasons or "failed_cost:expected_23bp" in reasons:
        return VERDICT_NO_GO_CONTROL
    if "failed_ablations" in reasons:
        return VERDICT_NO_GO_ABLATION
    if any(reason.startswith("failed_baseline") for reason in reasons):
        return VERDICT_NO_GO_BASELINE
    return VERDICT_INCONCLUSIVE


def _metrics(gate: RuleFilterGateInput) -> dict[str, float | int]:
    return {
        "validation_net_return_pct": float(gate.validation_net_return_pct),
        "oos_net_return_pct": float(gate.oos_net_return_pct),
        "oos_take_count": int(gate.oos_take_count),
        "max_drawdown_pct": float(gate.max_drawdown_pct),
        "max_allowed_drawdown_pct": float(gate.max_allowed_drawdown_pct),
        "min_oos_take_count": int(gate.min_oos_take_count),
        "skipped_opportunity_cost_pct": float(gate.skipped_opportunity_cost_pct),
    }


def _baseline_results(gate: RuleFilterGateInput) -> dict[str, dict[str, float | bool]]:
    return {
        "no_trade": _baseline_row(gate.oos_net_return_pct, gate.no_trade_net_return_pct),
        "buy_and_hold": _baseline_row(gate.oos_net_return_pct, gate.buy_and_hold_net_return_pct),
        "ts_imb_rule": _baseline_row(gate.oos_net_return_pct, gate.ts_imb_rule_net_return_pct),
    }


def _baseline_row(candidate: float, baseline: float) -> dict[str, float | bool]:
    return {"filter_net_return_pct": float(candidate), "baseline_net_return_pct": float(baseline), "passed": float(candidate) > float(baseline)}


def _equity_curve(gate: RuleFilterGateInput) -> list[dict[str, float | int]]:
    return [{"step": 0, "net_return_pct": 0.0}, {"step": 1, "net_return_pct": float(gate.oos_net_return_pct)}]


def _opportunity_cost_curve(gate: RuleFilterGateInput) -> list[dict[str, float | int]]:
    return [{"step": 0, "skipped_opportunity_cost_pct": 0.0}, {"step": 1, "skipped_opportunity_cost_pct": float(gate.skipped_opportunity_cost_pct)}]


def _time_buckets(gate: RuleFilterGateInput) -> list[dict[str, float | int | str]]:
    return [{"bucket": "0900-0930", "take_count": int(gate.oos_take_count), "net_return_pct": float(gate.oos_net_return_pct)}]
