"""Contracts for opening 30m RULE/meta-label filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypedDict

ACTION_TAKE: Final = "TAKE"
ACTION_SKIP: Final = "SKIP"
ActionLabel = Literal["TAKE", "SKIP"]

VERDICT_GO_RULE_FILTER: Final = "GO_RULE_FILTER"
VERDICT_NO_GO_BASELINE: Final = "NO-GO_BASELINE"
VERDICT_NO_GO_CONTROL: Final = "NO-GO_CONTROL"
VERDICT_NO_GO_ABLATION: Final = "NO-GO_ABLATION"
VERDICT_INCONCLUSIVE: Final = "INCONCLUSIVE"
RuleFilterVerdict = Literal[
    "GO_RULE_FILTER",
    "NO-GO_BASELINE",
    "NO-GO_CONTROL",
    "NO-GO_ABLATION",
    "INCONCLUSIVE",
]

RULE_FILTER_ARTIFACT_TYPE: Final = "opening_30m_rule_filter"
RULE_FILTER_BASELINE_LABEL: Final = "ts_imb RULE baseline"
FEATURE_SET_FULL_CONTEXT: Final = "full_context"
FEATURE_SET_MINIMAL_TS_IMB: Final = "minimal_ts_imb"
FEATURE_SET_TIME_BUCKET_ONLY: Final = "time_bucket_only"
RuleFilterFeatureSetId = Literal["full_context", "minimal_ts_imb", "time_bucket_only"]
RULE_FILTER_FEATURE_SET_IDS: Final[tuple[RuleFilterFeatureSetId, ...]] = (
    "full_context",
    "minimal_ts_imb",
    "time_bucket_only",
)
RULE_FILTER_TABLE_ALIASES: Final[tuple[str, ...]] = (
    "rule_filter_lifecycle",
    "rule_filter_splits",
    "rule_filter_controls",
    "rule_filter_ablations",
    "rule_filter_equity_curve",
    "rule_filter_time_buckets",
    "rule_filter_failure_reasons",
    "rule_filter_opportunity_cost",
    "rule_filter_proxy_availability",
    "rule_filter_orderbook_persistence",
    "rule_filter_context_sample",
)


@dataclass(frozen=True, slots=True)
class RuleFilterConfig:
    """Configuration for a bounded opening RULE filter."""

    cost_bps: float = 23.0
    min_oos_take_trades: int = 3
    decision_second: int = 0
    max_drawdown_pct: float = 5.0
    primary_baseline: str = RULE_FILTER_BASELINE_LABEL
    feature_set_id: RuleFilterFeatureSetId = FEATURE_SET_FULL_CONTEXT


class StrategyContext(TypedDict):
    line: str
    label: str
    primary_baseline: str
    is_reinforcement_learning: bool
    is_live_ready: bool
    is_profit_model: bool
    guardrail: str


def rule_filter_strategy_context() -> StrategyContext:
    """Return immutable research-only labeling for rule-filter artifacts."""

    return {
        "line": "rule_meta_label_filter",
        "label": "RULE META-LABEL FILTER",
        "primary_baseline": RULE_FILTER_BASELINE_LABEL,
        "is_reinforcement_learning": False,
        "is_live_ready": False,
        "is_profit_model": False,
        "guardrail": "RULE filter research only; not live-ready; proxy evidence only.",
    }
