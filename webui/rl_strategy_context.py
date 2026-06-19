"""Strategy-classification metadata for STOM RL dashboard payloads.

The dashboard compares rule baselines, cost/evaluation artifacts, and RL
experiments.  Keep that distinction server-computed so the UI does not infer
profitability or live readiness from artifact names.
"""

from __future__ import annotations

from typing import Any, Mapping

from stom_rl.gap_up_risk_sizing import PRIMARY_FILTER, RiskConfig, risk_unit_account_pct


RL_ARTIFACT_TYPES = frozenset({"contextual_bandit", "opening_30m_rl_workflow", "sb3_smoke"})
EVALUATION_ARTIFACT_TYPES = frozenset({"cost_gate", "performance_leaderboard", "episode_manifest", "portfolio_paper"})
GUARDRAIL = "research evidence only; not live-ready and not a profit model"


def risk_policy_summary(config: RiskConfig | None = None) -> dict[str, float | int | str]:
    """Return the locked ts_imb RULE sizing policy used as the main baseline."""

    policy = config or RiskConfig()
    return {
        "strategy": "opening_gap_up_rule",
        "primary_filter": PRIMARY_FILTER,
        "per_trade_fraction_pct": round(policy.per_trade_fraction * 100.0, 6),
        "max_concurrent": policy.max_concurrent,
        "max_deployed_fraction_pct": round(policy.per_trade_fraction * policy.max_concurrent * 100.0, 6),
        "daily_loss_limit_pct": policy.daily_loss_limit_pct,
        "cost_bps": policy.cost_bps,
        "tp_pct": policy.tp_pct,
        "sl_pct": policy.sl_pct,
        "risk_unit_account_pct": round(risk_unit_account_pct(policy), 6),
    }


def build_strategy_context(artifact_type: str, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Classify an RL-dashboard artifact without implying live readiness."""

    summary_map = dict(summary or {})
    if artifact_type == "baseline":
        return {
            "line": "rule_mainline",
            "label": "RULE MAINLINE",
            "primary_baseline": PRIMARY_FILTER,
            "is_reinforcement_learning": False,
            "is_environment_readiness": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": GUARDRAIL,
            "risk_policy_summary": risk_policy_summary(),
        }

    if artifact_type == "opening_30m_rule_filter":
        return {
            "line": "evaluation",
            "label": "RULE FILTER EVIDENCE",
            "primary_baseline": "ts_imb RULE baseline",
            "is_reinforcement_learning": False,
            "is_environment_readiness": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": GUARDRAIL,
            "readiness_status": summary_map.get("verdict"),
        }

    if artifact_type == "orderbook_rl_readiness":
        return {
            "line": "rl_experiment",
            "label": "RL EXPERIMENT",
            "primary_baseline": PRIMARY_FILTER,
            "is_reinforcement_learning": False,
            "is_environment_readiness": True,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": GUARDRAIL,
            "readiness_status": summary_map.get("readiness_status") or summary_map.get("verdict"),
        }

    if artifact_type in RL_ARTIFACT_TYPES:
        return {
            "line": "rl_experiment",
            "label": "RL EXPERIMENT",
            "primary_baseline": PRIMARY_FILTER,
            "is_reinforcement_learning": True,
            "is_environment_readiness": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": GUARDRAIL,
        }

    if artifact_type in EVALUATION_ARTIFACT_TYPES:
        return {
            "line": "evaluation",
            "label": "EVALUATION",
            "primary_baseline": PRIMARY_FILTER,
            "is_reinforcement_learning": False,
            "is_environment_readiness": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": GUARDRAIL,
        }

    return {
        "line": "unknown",
        "label": "UNKNOWN",
        "primary_baseline": PRIMARY_FILTER,
        "is_reinforcement_learning": False,
        "is_environment_readiness": False,
        "is_live_ready": False,
        "is_profit_model": False,
        "guardrail": GUARDRAIL,
    }
