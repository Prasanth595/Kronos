"""Participant proxy feature contract for opening-window research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypedDict


COL_TRADE_STRENGTH: Final[str] = "\uccb4\uacb0\uac15\ub3c4"
COL_BUY_AMOUNT: Final[str] = "\ucd08\ub2f9\ub9e4\uc218\uae08\uc561"
COL_SELL_AMOUNT: Final[str] = "\ucd08\ub2f9\ub9e4\ub3c4\uae08\uc561"
COL_TRANSACTION_VALUE: Final[str] = "\ucd08\ub2f9\uac70\ub798\ub300\uae08"
COL_BID_TOTAL: Final[str] = "\ub9e4\uc218\ucd1d\uc794\ub7c9"
COL_ASK_TOTAL: Final[str] = "\ub9e4\ub3c4\ucd1d\uc794\ub7c9"
COL_FOREIGN_NET_BUY: Final[str] = "\uc678\uad6d\uc778\uc21c\ub9e4\uc218"
COL_INSTITUTION_NET_BUY: Final[str] = "\uae30\uad00\uc21c\ub9e4\uc218"
COL_PROGRAM_NET_BUY: Final[str] = "\ud504\ub85c\uadf8\ub7a8\uc21c\ub9e4\uc218"

Availability = Literal["available", "missing"]
DecisionAvailability = Literal["required", "optional"]
MissingPolicy = Literal["fail_closed", "not_causal_at_decision"]


class ParticipantFeatureSpecPayload(TypedDict):
    name: str
    feature_group: str
    source_column: str
    available_at_decision_second: DecisionAvailability
    lookback: int
    missing_policy: MissingPolicy


class ParticipantComputedFeatures(TypedDict):
    rows_used: int
    transaction_value_sum: float
    transaction_value_surge: float
    signed_amount_ratio: float
    signed_amount_persistence: float
    trade_strength: float
    bid_depth_imbalance: float
    participant_proxy_pressure: float
    foreign_net_buy: float | None
    institution_net_buy: float | None
    program_net_buy: float | None


class ParticipantStrategyContext(TypedDict):
    line: str
    label: str
    is_reinforcement_learning: bool
    is_live_ready: bool
    is_profit_model: bool
    guardrail: str


class ParticipantReadinessPayload(TypedDict):
    artifact_type: str
    mode: str
    participant_context_version: str
    decision_second: int
    feature_schema: list[ParticipantFeatureSpecPayload]
    proxy_availability: dict[str, Availability]
    missing_proxy_columns: list[str]
    computed_features: ParticipantComputedFeatures
    strategy_context: ParticipantStrategyContext
    artifacts: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParticipantPressureError(ValueError):
    """Raised when participant proxy inputs violate causal feature contracts."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ParticipantProxyFeature:
    """Participant proxy schema item with causal source availability metadata."""

    name: str
    feature_group: str
    source_column: str
    required_columns: tuple[str, ...]
    available_at_decision_second: DecisionAvailability
    lookback: int
    missing_policy: MissingPolicy

    def to_payload(self) -> ParticipantFeatureSpecPayload:
        return {
            "name": self.name,
            "feature_group": self.feature_group,
            "source_column": self.source_column,
            "available_at_decision_second": self.available_at_decision_second,
            "lookback": int(self.lookback),
            "missing_policy": self.missing_policy,
        }


FEATURE_SPECS: Final[tuple[ParticipantProxyFeature, ...]] = (
    ParticipantProxyFeature("transaction_value_sum", "participant_pressure", COL_TRANSACTION_VALUE, (COL_TRANSACTION_VALUE,), "required", 30, "fail_closed"),
    ParticipantProxyFeature("signed_amount_ratio", "participant_pressure", f"{COL_BUY_AMOUNT}-{COL_SELL_AMOUNT}", (COL_BUY_AMOUNT, COL_SELL_AMOUNT), "required", 30, "fail_closed"),
    ParticipantProxyFeature("trade_strength", "participant_pressure", COL_TRADE_STRENGTH, (COL_TRADE_STRENGTH,), "required", 1, "fail_closed"),
    ParticipantProxyFeature("bid_depth_imbalance", "orderbook_persistence", f"{COL_BID_TOTAL}/{COL_ASK_TOTAL}", (COL_BID_TOTAL, COL_ASK_TOTAL), "required", 1, "fail_closed"),
    ParticipantProxyFeature("participant_proxy_pressure", "participant_pressure", "trade_strength+signed_amount_ratio+bid_depth_imbalance", (COL_TRADE_STRENGTH, COL_BUY_AMOUNT, COL_SELL_AMOUNT, COL_BID_TOTAL, COL_ASK_TOTAL), "required", 30, "fail_closed"),
    ParticipantProxyFeature("transaction_value_surge", "participant_pressure", COL_TRANSACTION_VALUE, (COL_TRANSACTION_VALUE,), "required", 30, "fail_closed"),
    ParticipantProxyFeature("signed_amount_persistence", "participant_pressure", f"{COL_BUY_AMOUNT}-{COL_SELL_AMOUNT}", (COL_BUY_AMOUNT, COL_SELL_AMOUNT), "required", 30, "fail_closed"),
    ParticipantProxyFeature("foreign_net_buy", "participant_flow_optional", COL_FOREIGN_NET_BUY, (COL_FOREIGN_NET_BUY,), "optional", 1, "not_causal_at_decision"),
    ParticipantProxyFeature("institution_net_buy", "participant_flow_optional", COL_INSTITUTION_NET_BUY, (COL_INSTITUTION_NET_BUY,), "optional", 1, "not_causal_at_decision"),
    ParticipantProxyFeature("program_net_buy", "participant_flow_optional", COL_PROGRAM_NET_BUY, (COL_PROGRAM_NET_BUY,), "optional", 1, "not_causal_at_decision"),
)
