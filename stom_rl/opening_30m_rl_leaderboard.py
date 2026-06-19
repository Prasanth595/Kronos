"""Cost-gate leaderboard row for opening 30-minute RL workflow artifacts."""

from __future__ import annotations

from typing import Any, Mapping


RULE_BASELINE_POLICY = "ts_imb_same_decision_tp5_sl1_time"


def evaluate_opening_workflow_leaderboard_row(
    *,
    run_id: str,
    rl_mean_return_pct: float,
    baseline_delta_inputs: Mapping[str, float],
    controls_payload: Mapping[str, Any],
    target_cost_bps: float = 23.0,
    trade_count: int,
    max_drawdown_pct: float,
) -> dict[str, Any]:
    """Evaluate one opening workflow row against controls, cost, and baselines."""

    rule_baseline = float(baseline_delta_inputs.get(RULE_BASELINE_POLICY, 0.0))
    buy_hold = float(baseline_delta_inputs.get("buy_and_hold", 0.0))
    best_baseline = max(rule_baseline, buy_hold, float(baseline_delta_inputs.get("no_trade", 0.0)))
    baseline_delta = float(rl_mean_return_pct) - best_baseline
    controls_blocked = bool(controls_payload.get("negative_control_blocked_go"))
    controls_passed = str(controls_payload.get("final_verdict")) == "GO_CANDIDATE" and not controls_blocked
    below_baseline = baseline_delta <= 0.0
    risk_ok = int(trade_count) > 0 and float(max_drawdown_pct) > -20.0
    passes_cost_gate = controls_passed and not below_baseline and risk_ok and float(target_cost_bps) == 23.0
    if controls_blocked:
        decision = "NO-GO"
    elif below_baseline:
        decision = "below_baseline"
    else:
        decision = "GO_CANDIDATE" if passes_cost_gate else "NO-GO"
    return {
        "run_id": run_id,
        "artifact_type": "opening_30m_leaderboard_row",
        "target_cost_bps": float(target_cost_bps),
        "rl_mean_return_pct": float(rl_mean_return_pct),
        "baseline_policy": RULE_BASELINE_POLICY,
        "best_baseline_return_pct": best_baseline,
        "baseline_delta_pct": baseline_delta,
        "below_rule_baseline": float(rl_mean_return_pct) <= rule_baseline,
        "negative_control_blocked_go": controls_blocked,
        "controls_passed": controls_passed,
        "passes_cost_gate": passes_cost_gate,
        "trade_count": int(trade_count),
        "max_drawdown_pct": float(max_drawdown_pct),
        "decision": decision,
        "strategy_context": {
            "line": "opening_rl_leaderboard",
            "label": "RL EXPERIMENT LEADERBOARD",
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }
